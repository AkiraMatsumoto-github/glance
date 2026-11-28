"""サイトと Search Console・Bing の紐づけ（technical_design.md §6.4）。"""

import httpx
import psycopg
import pytest
from httpx import AsyncClient
from sqlalchemy.engine import make_url

from glance.bing import BingKeyInvalid, BingUnavailable, FakeBingClient, RealBingClient
from glance.google.fake import FakeGa4Client
from glance.google.ga4 import GscApiDisabled
from glance.sites.links import match_gsc_site

JSON = {"content-type": "application/json"}
SITES_A = ["https://a.example/", "https://b.example/"]
SITES_B = ["https://c.example/"]


def _query(database_url: str, sql: str) -> list[tuple]:
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url) as conn:
        return conn.execute(sql).fetchall()


async def add(client: AsyncClient, property_id: str, gsc_site_url: str | None = None) -> dict:
    response = await client.post("/api/sites", json={"property_id": property_id, "gsc_site_url": gsc_site_url})
    assert response.status_code == 201, response.text
    return response.json()


def test_match_gsc_site() -> None:
    sites = ["sc-domain:example.com", "https://www.example.com/", "https://other.example/", "sc-domain:blog.example.com"]
    # ドメインのプロパティを選ぶ。いくつか合うときは、いちばん細かいドメイン
    assert match_gsc_site(["www.example.com"], sites) == "sc-domain:example.com"
    assert match_gsc_site(["blog.example.com"], sites) == "sc-domain:blog.example.com"
    # ドメインのプロパティがなければ、同じホスト（www. の有無は問わない）の URL のプロパティが1つだけのとき
    assert match_gsc_site(["other.example"], sites) == "https://other.example/"
    assert match_gsc_site(["www.other.example"], ["https://other.example/"]) == "https://other.example/"
    assert match_gsc_site(["x.example"], ["https://x.example/", "http://x.example/"]) is None
    assert match_gsc_site(["none.example"], sites) is None
    assert match_gsc_site([], sites) is None


# --- Search Console -------------------------------------------------------------------------


async def test_properties_suggest_gsc_site(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000005")
    props = {p["property_id"]: p for a in (await logged_in.get("/api/ga4/properties")).json() for p in a["properties"]}
    # LogiShift はドメインと URL の両方があり、ドメインを選ぶ。TechShift は URL だけ。ConShift は見つからない
    assert props["900000001"]["search_console"]["site_url"] == "sc-domain:logishift.example"
    assert props["900000002"]["search_console"]["site_url"] == "https://techshift.example/"
    assert props["900000003"]["search_console"]["site_url"] is None
    assert "sc-domain:finshift.example" in props["900000003"]["search_console"]["candidates"]
    # 追加済みのプロパティには出さない
    assert props["900000005"]["search_console"] is None


async def test_add_site_with_gsc_site(logged_in: AsyncClient, database_url: str) -> None:
    site = await add(logged_in, "900000001", "sc-domain:logishift.example")
    assert site["links"] == {"gsc_site_url": "sc-domain:logishift.example", "bing_site_url": None, "bing_key_id": None}
    assert _query(database_url, "SELECT source, auth_method, user_id FROM connections ORDER BY source") == [
        ("ga4", "google", 1),
        ("gsc", "google", 1),
    ]
    # 見られないサイトは受け付けず、サイトも作らない
    bad = await logged_in.post("/api/sites", json={"property_id": "900000002", "gsc_site_url": "sc-domain:nope.example"})
    assert bad.status_code == 400
    assert bad.json()["code"] == "unknown_gsc_site"
    assert len((await logged_in.get("/api/sites")).json()) == 1


async def test_link_and_unlink_gsc(logged_in: AsyncClient, database_url: str) -> None:
    site = await add(logged_in, "900000002")
    choice = (await logged_in.get(f"/api/sites/{site['id']}/gsc")).json()
    assert choice["current"] is None
    assert choice["suggested"] == "https://techshift.example/"
    assert choice["suggested"] in choice["candidates"]

    linked = await logged_in.put(f"/api/sites/{site['id']}/gsc", json={"site_url": choice["suggested"]})
    assert linked.status_code == 200
    assert (await logged_in.get("/api/sites")).json()[0]["links"]["gsc_site_url"] == "https://techshift.example/"
    assert _query(database_url, "SELECT count(*) FROM connections WHERE source = 'gsc'") == [(1,)]

    bad = await logged_in.put(f"/api/sites/{site['id']}/gsc", json={"site_url": "sc-domain:nope.example"})
    assert bad.json()["code"] == "unknown_gsc_site"

    await logged_in.put(f"/api/sites/{site['id']}/gsc", json={"site_url": None})
    assert (await logged_in.get("/api/sites")).json()[0]["links"]["gsc_site_url"] is None
    assert _query(database_url, "SELECT count(*) FROM connections WHERE source = 'gsc'") == [(0,)]


class GscDisabled(FakeGa4Client):
    async def list_gsc_sites(self) -> list[str]:
        raise GscApiDisabled()


@pytest.mark.parametrize("ga4", [GscDisabled(latency=(0, 0))])
async def test_gsc_api_disabled(logged_in: AsyncClient) -> None:
    # GA4 のプロパティの追加はできる。Search Console を選ぶところで、有効にするよう伝える
    props = [p for a in (await logged_in.get("/api/ga4/properties")).json() for p in a["properties"]]
    assert all(p["search_console"] is None for p in props)
    site = await add(logged_in, "900000001")
    response = await logged_in.get(f"/api/sites/{site['id']}/gsc")
    assert response.status_code == 503
    assert response.json()["code"] == "gsc_api_disabled"


# --- Bing ------------------------------------------------------------------------------------


@pytest.mark.parametrize("bing", [FakeBingClient({"key-aaaa-1111": SITES_A, "key-bbbb-2222": SITES_B})])
async def test_bing_keys_and_link(logged_in: AsyncClient, database_url: str) -> None:
    site = await add(logged_in, "900000001")

    # 使えないキーは保存しない
    bad = await logged_in.post("/api/bing/keys", json={"name": "LogiShift 用", "key": "key-wrong-0000"})
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid_bing_key"

    created = await logged_in.post("/api/bing/keys", json={"name": " LogiShift 用 ", "key": "key-aaaa-1111"})
    assert created.status_code == 201
    key = created.json()
    # キーそのものは返さず、DB にも暗号化して入れる
    assert key == {"id": key["id"], "name": "LogiShift 用", "last4": "1111"}
    [(stored,)] = _query(database_url, "SELECT key_encrypted FROM bing_keys")
    assert "key-aaaa-1111" not in stored
    dup = await logged_in.post("/api/bing/keys", json={"name": "LogiShift 用", "key": "key-bbbb-2222"})
    assert dup.json()["code"] == "name_taken"
    assert (await logged_in.get("/api/bing/keys")).json() == [key]
    assert (await logged_in.get(f"/api/bing/keys/{key['id']}/sites")).json() == SITES_A

    # 紐づける。キーで見られないサイトは受け付けない
    no_key = await logged_in.put(f"/api/sites/{site['id']}/bing", json={"site_url": SITES_A[0]})
    assert no_key.json()["code"] == "key_required"
    other = await logged_in.put(f"/api/sites/{site['id']}/bing", json={"key_id": key["id"], "site_url": SITES_B[0]})
    assert other.json()["code"] == "unknown_bing_site"
    linked = await logged_in.put(f"/api/sites/{site['id']}/bing", json={"key_id": key["id"], "site_url": SITES_A[0]})
    assert linked.status_code == 200
    links = (await logged_in.get("/api/sites")).json()[0]["links"]
    assert links["bing_site_url"] == SITES_A[0]
    assert links["bing_key_id"] == key["id"]
    assert _query(database_url, "SELECT auth_method, user_id, bing_key_id FROM connections WHERE source = 'bing'") == [
        ("api_key", None, key["id"])
    ]

    # 入れ直す。使えないキーなら前のまま
    assert (await logged_in.put(f"/api/bing/keys/{key['id']}", json={"key": "key-wrong-0000"})).status_code == 400
    updated = await logged_in.put(f"/api/bing/keys/{key['id']}", json={"key": "key-bbbb-2222"})
    assert updated.json()["last4"] == "2222"
    assert (await logged_in.get(f"/api/bing/keys/{key['id']}/sites")).json() == SITES_B

    # 外す。取り込んだ数字のために、サイトの紐づけ以外（キー）は残す
    await logged_in.put(f"/api/sites/{site['id']}/bing", json={"key_id": None, "site_url": None})
    links = (await logged_in.get("/api/sites")).json()[0]["links"]
    assert (links["bing_site_url"], links["bing_key_id"]) == (None, None)
    assert _query(database_url, "SELECT count(*) FROM connections WHERE source = 'bing'") == [(0,)]
    assert len((await logged_in.get("/api/bing/keys")).json()) == 1


async def test_other_tenant_cannot_use_links(logged_in: AsyncClient, database_url: str) -> None:
    site = await add(logged_in, "900000001")
    key = (await logged_in.post("/api/bing/keys", json={"name": "k", "key": "good-key-1234"})).json()
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("INSERT INTO tenants (id, name) VALUES (2, '別の顧客')")
        conn.execute("UPDATE users SET tenant_id = 2")
    assert (await logged_in.get("/api/bing/keys")).json() == []
    assert (await logged_in.get(f"/api/bing/keys/{key['id']}/sites")).status_code == 404
    assert (await logged_in.put(f"/api/bing/keys/{key['id']}", json={"key": "good-key-5678"})).status_code == 404
    assert (await logged_in.get(f"/api/sites/{site['id']}/gsc")).status_code == 404
    response = await logged_in.put(f"/api/sites/{site['id']}/bing", json={"key_id": key["id"], "site_url": None})
    assert response.status_code == 404


async def test_links_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/bing/keys")).status_code == 401
    assert (await client.post("/api/bing/keys", json={"name": "k", "key": "good-key-1234"})).status_code == 401
    assert (await client.get("/api/sites/1/gsc")).status_code == 401
    assert (await client.put("/api/sites/1/bing", json={"site_url": None})).status_code == 401


# --- 本物の Bing クライアント（HTTP を差し替える） -------------------------------------------


async def test_real_bing_client() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["apikey"])
        if request.url.params["apikey"] == "bad":
            return httpx.Response(400, json={"ErrorCode": 3, "Message": "InvalidApiKey"})
        if request.url.params["apikey"] == "down":
            return httpx.Response(503)
        return httpx.Response(
            200, json={"d": [{"Url": "https://b.example/", "IsVerified": True}, {"Url": "https://x.example/", "IsVerified": False}]}
        )

    client = RealBingClient(transport=httpx.MockTransport(handler))
    assert await client.list_sites("good") == ["https://b.example/"]
    with pytest.raises(BingKeyInvalid):
        await client.list_sites("bad")
    with pytest.raises(BingUnavailable):
        await client.list_sites("down")
    assert seen == ["good", "bad", "down"]


async def test_real_bing_client_hides_key_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = RealBingClient(transport=httpx.MockTransport(handler))
    with pytest.raises(BingUnavailable) as info:
        await client.list_sites("secret-key-9999")
    # 元の例外（キーを含む URL を持つ）をつなげない
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True

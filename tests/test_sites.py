from httpx import AsyncClient

from tests.conftest import JSON, add_site, db_query

async def test_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/sites")).status_code == 401
    assert (await client.get("/api/ga4/properties")).status_code == 401


async def test_list_properties_marks_added(logged_in: AsyncClient) -> None:
    await add_site(logged_in, "900000001")
    accounts = (await logged_in.get("/api/ga4/properties")).json()
    assert [a["name"] for a in accounts] == ["ダミーのアカウント 1", "ダミーのアカウント 2"]
    props = {p["property_id"]: p for a in accounts for p in a["properties"]}
    assert props["900000001"]["added"] is True
    assert props["900000002"]["added"] is False


async def test_add_site_takes_name_and_timezone_from_property(logged_in: AsyncClient, database_url: str) -> None:
    site = await add_site(logged_in, "900000002")
    assert site["name"] == "TechShift"
    assert db_query(database_url, "SELECT timezone, sort_order FROM sites") == [("Asia/Tokyo", 0)]
    assert db_query(database_url, "SELECT source, auth_method FROM connections") == [("ga4", "google")]


async def test_add_site_twice_is_rejected(logged_in: AsyncClient) -> None:
    await add_site(logged_in, "900000001")
    response = await logged_in.post("/api/sites", json={"property_id": "900000001"})
    assert response.status_code == 409
    assert response.json()["code"] == "already_added"


async def test_add_unknown_property_is_rejected(logged_in: AsyncClient) -> None:
    response = await logged_in.post("/api/sites", json={"property_id": "123"})
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    bad = await logged_in.post("/api/sites", json={"property_id": "abc"})
    assert bad.status_code == 422


async def test_rename_move_delete(logged_in: AsyncClient, database_url: str) -> None:
    a = await add_site(logged_in, "900000001")
    b = await add_site(logged_in, "900000002")
    c = await add_site(logged_in, "900000003")

    renamed = await logged_in.patch(f"/api/sites/{b['id']}", json={"name": "  テック  "})
    assert renamed.json()["name"] == "テック"
    assert (await logged_in.patch(f"/api/sites/{b['id']}", json={"name": "   "})).status_code == 422

    await logged_in.patch(f"/api/sites/{c['id']}", json={"position": 0})
    order = [s["id"] for s in (await logged_in.get("/api/sites")).json()]
    assert order == [c["id"], a["id"], b["id"]]

    await logged_in.patch(f"/api/sites/{c['id']}", json={"position": 99})
    sites = (await logged_in.get("/api/sites")).json()
    assert [s["id"] for s in sites] == [a["id"], b["id"], c["id"]]
    assert db_query(database_url, "SELECT id, sort_order FROM sites ORDER BY sort_order") == [
        (a["id"], 0), (b["id"], 1), (c["id"], 2)
    ]

    response = await logged_in.delete(f"/api/sites/{a['id']}", headers=JSON)
    assert response.status_code == 204
    assert [s["id"] for s in (await logged_in.get("/api/sites")).json()] == [b["id"], c["id"]]
    # 消した後も、並びの位置は 0 から詰める
    assert db_query(database_url, "SELECT id, sort_order FROM sites ORDER BY sort_order") == [(b["id"], 0), (c["id"], 1)]
    assert (await logged_in.delete(f"/api/sites/{a['id']}", headers=JSON)).status_code == 404


async def test_other_tenant_cannot_see_sites(logged_in: AsyncClient, database_url: str) -> None:
    site = await add_site(logged_in, "900000001")
    db_query(database_url, "INSERT INTO tenants (id, name) VALUES (2, '別の顧客')")
    db_query(database_url, "UPDATE users SET tenant_id = 2")
    assert (await logged_in.get("/api/sites")).json() == []
    assert (await logged_in.patch(f"/api/sites/{site['id']}", json={"name": "x"})).status_code == 404
    assert (await logged_in.delete(f"/api/sites/{site['id']}", headers=JSON)).status_code == 404


async def test_demo_sites_need_no_login_and_touch_no_data(client: AsyncClient, database_url: str) -> None:
    sites = await client.get("/api/demo/sites")
    assert sites.status_code == 200
    assert [s["name"] for s in sites.json()] == ["デモサイト A", "デモサイト B", "デモサイト C", "デモサイト D", "デモサイト E"]
    properties = await client.get("/api/demo/ga4/properties")
    assert properties.status_code == 200
    listed = [(p["name"], p["added"]) for a in properties.json() for p in a["properties"]]
    # 追加済みはデモの5サイト。未追加の見え方を見せるためのものが1つ
    assert [name for name, added in listed if added] == [s["name"] for s in sites.json()]
    assert [name for name, added in listed if not added] == ["デモサイト F"]
    # デモの5サイトは、Search Console と Bing を紐づけ済み。紐づけ先は、選べる一覧の中にある
    keys = (await client.get("/api/demo/bing/keys")).json()
    assert [set(k) for k in keys] == [{"id", "name", "last4"}]
    for site in sites.json():
        gsc = (await client.get(f"/api/demo/sites/{site['id']}/gsc")).json()
        assert site["links"]["gsc_site_url"] == gsc["current"] == gsc["suggested"]
        assert gsc["current"] in gsc["candidates"]
        bing = (await client.get(f"/api/demo/bing/keys/{site['links']['bing_key_id']}/sites")).json()
        assert site["links"]["bing_site_url"] in bing
    # F は Search Console のサイトが見つからない例。選べる一覧は出す
    not_added = next(p for a in properties.json() for p in a["properties"] if not p["added"])
    assert not_added["search_console"]["site_url"] is None
    assert not_added["search_console"]["candidates"] == gsc["candidates"]
    # デモには書き込みの API がない
    assert (await client.post("/api/demo/sites", json={"property_id": "900000006"})).status_code in (404, 405)
    assert (await client.post("/api/demo/bing/keys", json={"name": "x", "key": "12345678"})).status_code in (404, 405)
    assert db_query(database_url, "SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM sites)") == [(0, 0)]

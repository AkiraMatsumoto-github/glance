import asyncio

import pytest
from httpx import AsyncClient

from glance.google.fake import ERROR_PROPERTY_ID, FakeGa4Client
from glance.google.ga4 import Ga4PermissionDenied, Ga4QuotaExceeded, MinuteRow, ReauthRequired


async def add(client: AsyncClient, property_id: str) -> None:
    response = await client.post("/api/sites", json={"property_id": property_id})
    assert response.status_code == 201, response.text


async def test_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/realtime")).status_code == 401


async def test_no_sites(logged_in: AsyncClient) -> None:
    body = (await logged_in.get("/api/realtime")).json()
    assert body["sites"] == []
    assert body["fetched_at"].endswith("+09:00")


async def test_sites_in_order_with_filled_minutes(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000001")
    await add(logged_in, "900000002")
    body = (await logged_in.get("/api/realtime")).json()
    assert [s["name"] for s in body["sites"]] == ["LogiShift", "TechShift"]
    for site in body["sites"]:
        assert site["status"] == "ok"
        assert [m["minutes_ago"] for m in site["per_minute"]] == list(range(29, -1, -1))
        assert len(site["top_pages"]) <= 20


async def test_device_and_country_breakdowns(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000001")
    site = (await logged_in.get("/api/realtime")).json()["sites"][0]
    devices = {d["key"] for d in site["devices"]}
    assert devices <= {"mobile", "desktop", "tablet"} and "mobile" in devices
    countries = site["countries"]
    assert 0 < len(countries) <= 10
    assert countries[0]["key"] == "JP"
    assert [c["active_users"] for c in countries] == sorted((c["active_users"] for c in countries), reverse=True)
    # デバイス・国はユーザーの属性なので UU だけ
    for row in site["devices"] + countries:
        assert set(row) == {"key", "active_users"}


async def test_events(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000001")
    site = (await logged_in.get("/api/realtime")).json()["sites"][0]
    events = site["events"]
    assert 0 < len(events) <= 20
    assert set(events[0]) == {"name", "event_count"}
    assert [e["event_count"] for e in events] == sorted((e["event_count"] for e in events), reverse=True)
    # page_view の回数は PV と同じ
    page_view = next(e for e in events if e["name"] == "page_view")
    assert page_view["event_count"] == site["last_30_min"]["page_views"]


async def test_failed_site_does_not_break_others(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000001")
    await add(logged_in, ERROR_PROPERTY_ID)
    body = (await logged_in.get("/api/realtime")).json()
    ok, failed = body["sites"]
    assert ok["status"] == "ok"
    assert failed == {"site_id": failed["site_id"], "name": failed["name"], "status": "error", "error": "timeout"}
    assert set(body) == {"fetched_at", "sites"}


class SparseFake(FakeGa4Client):
    """値のない分を抜いた分ごとの行を返す。"""

    async def realtime_per_minute(self, property_id: str) -> list[MinuteRow]:
        return [MinuteRow(0, 5, 3), MinuteRow(10, 2, 2)]


@pytest.mark.parametrize("ga4", [SparseFake(latency=(0, 0))])
async def test_missing_minutes_are_zero(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000001")
    minutes = (await logged_in.get("/api/realtime")).json()["sites"][0]["per_minute"]
    values = {m["minutes_ago"]: (m["page_views"], m["active_users"]) for m in minutes}
    assert values[0] == (5, 3)
    assert values[10] == (2, 2)
    assert values[1] == (0, 0)


class RaisingFake(FakeGa4Client):
    def __init__(self, error: BaseException) -> None:
        super().__init__(latency=(0, 0))
        self.error = error

    async def realtime_top_pages(self, property_id: str, limit: int):  # type: ignore[no-untyped-def]
        raise self.error


@pytest.mark.parametrize(
    ("ga4", "code"),
    [
        (RaisingFake(Ga4PermissionDenied()), "permission_denied"),
        (RaisingFake(Ga4QuotaExceeded()), "quota"),
        (RaisingFake(RuntimeError("boom")), "error"),
    ],
)
async def test_error_kinds(logged_in: AsyncClient, code: str) -> None:
    await add(logged_in, "900000001")
    site = (await logged_in.get("/api/realtime")).json()["sites"][0]
    assert site["status"] == "error"
    assert site["error"] == code


@pytest.mark.parametrize("ga4", [RaisingFake(ReauthRequired())])
async def test_reauth_required(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000001")
    response = await logged_in.get("/api/realtime")
    assert response.status_code == 401
    assert response.json()["code"] == "reauth_required"


class SlowFake(FakeGa4Client):
    async def realtime_totals(self, property_id: str):  # type: ignore[no-untyped-def]
        await asyncio.sleep(5)
        return await super().realtime_totals(property_id)


@pytest.mark.parametrize("ga4", [SlowFake(latency=(0, 0))])
async def test_slow_site_times_out(logged_in: AsyncClient) -> None:
    await add(logged_in, "900000001")
    site = (await logged_in.get("/api/realtime")).json()["sites"][0]
    assert site["error"] == "timeout"


async def test_demo_needs_no_login_and_touches_no_data(client: AsyncClient, database_url: str) -> None:
    import psycopg
    from sqlalchemy.engine import make_url

    response = await client.get("/api/demo/realtime")
    assert response.status_code == 200
    body = response.json()
    assert [s["name"] for s in body["sites"]] == ["デモサイト A", "デモサイト B", "デモサイト C", "デモサイト D", "デモサイト E"]
    assert all(s["status"] == "ok" for s in body["sites"])
    assert response.headers["cache-control"] == "no-store"
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM sites)").fetchone() == (0, 0)

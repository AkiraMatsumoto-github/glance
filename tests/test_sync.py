"""Search Console・Bing の取り込み（glance.sync）と、取り込んだ表からの集計（GET /api/seo）。"""

from datetime import date, timedelta

import psycopg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.engine import make_url

from glance.google.fake import FakeGa4Client
from glance.google.ga4 import Ga4QuotaExceeded, GscRow
from glance.sync import runner
from glance.sync.runner import Syncer, gsc_values, months_ago
from glance.sync.sitemap import FakeSitemapFetcher, sitemap_paths
from glance.sync.values import bing_date, country_code, device, page_path

TODAY = date(2026, 11, 20)


def _query(database_url: str, sql: str, params: tuple = ()) -> list[tuple]:
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True) as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


def syncer(app: FastAPI, today: date = TODAY) -> Syncer:
    return Syncer(
        app.state.sessionmaker,
        app.state.ga4_factory,
        app.state.bing_client,
        app.state.cipher,
        today,
        sitemap_fetcher=FakeSitemapFetcher(),
    )


async def linked_site(client: AsyncClient) -> dict:
    """LogiShift を追加し、Search Console と Bing を紐づける。"""
    site = (await client.post("/api/sites", json={"property_id": "900000001", "gsc_site_url": "sc-domain:logishift.example"})).json()
    key = (await client.post("/api/bing/keys", json={"name": "k", "key": "good-key-1234"})).json()
    linked = await client.put(f"/api/sites/{site['id']}/bing", json={"key_id": key["id"], "site_url": "https://www.logishift.example/"})
    assert linked.status_code == 200
    return site


@pytest.fixture(autouse=True)
def short_backfill(monkeypatch: pytest.MonkeyPatch) -> None:
    # テストでは、初めの取り込みを1ヶ月前からにし（本物は16ヶ月）、上限に当たったときに待たない
    monkeypatch.setattr(runner, "BACKFILL_MONTHS", 1)
    monkeypatch.setattr(runner, "GSC_BACKOFF_SECONDS", 0)


def test_values() -> None:
    assert page_path("https://www.example.com/tools/%E5%80%89%E5%BA%AB/?utm=x#top") == "/tools/倉庫/"
    assert page_path("https://example.com") == "/"
    assert (country_code("jpn"), country_code("USA"), country_code("zzz")) == ("JP", "US", "(not set)")
    assert device("MOBILE") == "mobile"
    # 太平洋時間の0時（UTC の8時）は、その日
    assert bing_date("/Date(1794816000000-0800)/") == date(2026, 11, 16)
    assert bing_date("/Date(1794787200000)/") == date(2026, 11, 16)
    assert months_ago(date(2026, 3, 31), 16) == date(2024, 11, 1)


def test_gsc_values_merge_same_path() -> None:
    rows = [
        GscRow(["2026-11-01", "https://a.example/x?p=1"], clicks=2, impressions=10, position=2.0),
        GscRow(["2026-11-01", "https://a.example/x"], clicks=1, impressions=30, position=6.0),
    ]
    [value] = gsc_values(1, ["date", "page"], rows)
    assert (value["page"], value["clicks"], value["impressions"]) == ("/x", 3, 40)
    assert value["position_weighted"] == 2.0 * 10 + 6.0 * 30
    assert value["position"] == pytest.approx(5.0)


async def test_sync_fills_tables_and_logs(app: FastAPI, logged_in: AsyncClient, database_url: str) -> None:
    site = await linked_site(logged_in)
    outcomes = await syncer(app).run({"gsc", "bing"})
    assert all(o.error is None for o in outcomes), outcomes
    start = months_ago(TODAY, 1)
    assert _query(database_url, "SELECT min(date), max(date), count(DISTINCT country) FROM gsc_site") == [(start, TODAY, 3)]
    assert set(_query(database_url, "SELECT DISTINCT country FROM gsc_site")) == {("(not set)",), ("JP",), ("US",)}
    assert set(_query(database_url, "SELECT DISTINCT device FROM gsc_page")) == {("desktop",), ("mobile",)}
    assert ("/tools/倉庫/",) in _query(database_url, "SELECT DISTINCT page FROM gsc_query_page")
    # Bing は取れる範囲の全部（日次98日・ページ別13週×3ページ）
    assert _query(database_url, "SELECT count(*) FROM bing_site_daily") == [(98,)]
    assert _query(database_url, "SELECT count(*) FROM bing_crawl_daily") == [(98,)]
    assert _query(database_url, "SELECT count(*), count(DISTINCT page) FROM bing_page_weekly") == [(39, 3)]
    assert _query(database_url, "SELECT raw->>'Clicks' IS NOT NULL FROM bing_site_daily LIMIT 1") == [(True,)]
    runs = _query(database_url, "SELECT source, table_name, ok FROM sync_runs WHERE site_id = %s ORDER BY id", (site["id"],))
    assert {(s, t) for s, t, _ in runs} == {
        ("gsc", "gsc_site"), ("gsc", "gsc_page"), ("gsc", "gsc_query_page"), ("gsc", "gsc_query_cleanup"),
        ("gsc", "sitemap_urls"),
        ("bing", "bing_site_daily"), ("bing", "bing_page_weekly"), ("bing", "bing_crawl_daily"),
    }
    assert all(ok for _, _, ok in runs)

    # 次は、取得済みの最終日の3日前から取り直す
    later = TODAY + timedelta(days=2)
    await syncer(app, later).run({"gsc"})
    [(again,)] = _query(database_url, "SELECT start_date FROM sync_runs WHERE table_name = 'gsc_site' ORDER BY id DESC LIMIT 1")
    assert again == TODAY - timedelta(days=3)
    assert _query(database_url, "SELECT max(date) FROM gsc_site") == [(later,)]


async def test_sync_cleans_small_queries_after_month_closes(app: FastAPI, logged_in: AsyncClient, database_url: str) -> None:
    site = await linked_site(logged_in)
    # 11月5日の時点では、10月はまだ整理しない（翌月8日から）
    await syncer(app, date(2026, 11, 5)).run({"gsc"})
    # 10月と11月に、表示回数が10回未満のクエリを置く。11月20日に取り込むと、10月の分だけ消える
    for day in ("2026-10-20", "2026-11-01"):
        _query(
            database_url,
            "INSERT INTO gsc_query_page VALUES (%s, %s, 'まれなクエリ', '/', 0, 3, 5, 15)",
            (site["id"], day),
        )
    await syncer(app).run({"gsc"})
    assert _query(database_url, "SELECT date FROM gsc_query_page WHERE query = 'まれなクエリ'") == [(date(2026, 11, 1),)]
    assert _query(
        database_url, "SELECT start_date FROM sync_runs WHERE table_name = 'gsc_query_cleanup' AND rows > 0"
    ) == [(date(2026, 10, 1),)]


class FailingOnce(FakeGa4Client):
    def __init__(self) -> None:
        super().__init__(latency=(0, 0))
        self.fail_on: date | None = TODAY - timedelta(days=5)

    async def gsc_search_analytics(self, site_url, start, end, dimensions, start_row, row_limit):  # type: ignore[no-untyped-def]
        if start == self.fail_on:
            raise TimeoutError("時間切れ")
        return await super().gsc_search_analytics(site_url, start, end, dimensions, start_row, row_limit)


@pytest.mark.parametrize("ga4", [FailingOnce()])
async def test_sync_stops_at_failure_and_resumes(app: FastAPI, ga4: FailingOnce, logged_in: AsyncClient, database_url: str) -> None:
    await linked_site(logged_in)
    outcomes = await syncer(app).run({"gsc"})
    failed = [o for o in outcomes if o.error]
    assert {o.table for o in failed} == {"gsc_site", "gsc_page", "gsc_query_page"}
    assert all("時間切れ" in (o.error or "") for o in failed)
    # 失敗した日の前の日までで止まる
    assert _query(database_url, "SELECT max(date) FROM gsc_site") == [(TODAY - timedelta(days=6),)]
    ga4.fail_on = None
    assert all(o.error is None for o in await syncer(app).run({"gsc"}))
    assert _query(database_url, "SELECT max(date) FROM gsc_site") == [(TODAY,)]


class QuotaTwice(FakeGa4Client):
    """同じ日の1回目と2回目は上限に当たる。"""

    def __init__(self) -> None:
        super().__init__(latency=(0, 0))
        self.calls: dict[tuple, int] = {}

    async def gsc_search_analytics(self, site_url, start, end, dimensions, start_row, row_limit):  # type: ignore[no-untyped-def]
        key = (start, tuple(dimensions))
        self.calls[key] = self.calls.get(key, 0) + 1
        if self.calls[key] <= 2:
            raise Ga4QuotaExceeded("Quota exceeded")
        return await super().gsc_search_analytics(site_url, start, end, dimensions, start_row, row_limit)


@pytest.mark.parametrize("ga4", [QuotaTwice()])
async def test_sync_retries_on_quota(app: FastAPI, ga4: QuotaTwice, logged_in: AsyncClient, database_url: str) -> None:
    await linked_site(logged_in)
    assert all(o.error is None for o in await syncer(app).run({"gsc"}))
    assert set(ga4.calls.values()) == {3}
    assert _query(database_url, "SELECT max(date) FROM gsc_site") == [(TODAY,)]


class NoDataUntil(FakeGa4Client):
    """サイトを始める前（数字が無い）の期間がある。"""

    def __init__(self) -> None:
        super().__init__(latency=(0, 0))
        self.first = TODAY - timedelta(days=5)
        self.asked: list[date] = []

    async def gsc_search_analytics(self, site_url, start, end, dimensions, start_row, row_limit):  # type: ignore[no-untyped-def]
        self.asked.append(start)
        if start == TODAY:
            raise TimeoutError("時間切れ")
        if start < self.first:
            return []
        return await super().gsc_search_analytics(site_url, start, end, dimensions, start_row, row_limit)


@pytest.mark.parametrize("ga4", [NoDataUntil()])
async def test_sync_resumes_after_empty_period(app: FastAPI, ga4: NoDataUntil, logged_in: AsyncClient) -> None:
    await linked_site(logged_in)
    ga4.first = TODAY + timedelta(days=1)  # 1回目は、どの日も数字が無いうえ、今日で失敗する
    await syncer(app).run({"gsc"})
    ga4.asked.clear()
    await syncer(app).run({"gsc"})
    # 取り終えた日（昨日）の3日前から続ける。数字が無くても最初からは取り直さない
    assert min(ga4.asked) == TODAY - timedelta(days=4)


# --- GET /api/seo ----------------------------------------------------------------------------


async def test_seo_report(app: FastAPI, logged_in: AsyncClient, database_url: str) -> None:
    empty = (await logged_in.get("/api/seo")).json()
    assert (empty["sites"], empty["data_until"]) == ([], None)

    site = await linked_site(logged_in)
    await logged_in.post("/api/sites", json={"property_id": "900000002"})  # 紐づけていないサイトは出さない
    await syncer(app, date.today()).run({"gsc", "bing"})

    google = (await logged_in.get("/api/seo", params={"period": "last_7_days"})).json()
    assert [s["name"] for s in google["sites"]] == ["LogiShift"]
    assert google["data_until"] == date.today().isoformat()
    report = google["sites"][0]
    start, end = google["period"]["start"], google["period"]["end"]
    [(clicks, impressions, weighted)] = _query(
        database_url,
        "SELECT sum(clicks), sum(impressions), sum(position_weighted) FROM gsc_site WHERE site_id = %s AND date BETWEEN %s AND %s",
        (site["id"], start, end),
    )
    assert report["totals"] == {"clicks": clicks, "impressions": impressions, "position": round(weighted / impressions, 1)}
    assert len(report["daily"]) == 7 and len(report["compare_daily"]) == 7
    assert sum(d["clicks"] for d in report["daily"]) == clicks
    # クエリ・ページはクリックの多い順。比べる期間のクリックが付く。ページのタイトルは無く、パスを出す
    assert [q["clicks"] for q in report["queries"]] == sorted((q["clicks"] for q in report["queries"]), reverse=True)
    assert all(q["compare_clicks"] is not None for q in report["queries"])
    assert {p["path"] for p in report["pages"]} == {"/", "/glossary/wms/", "/news/2024-problem/", "/tools/倉庫/"}
    assert all(p["title"] is None for p in report["pages"])
    assert report["crawl"] is None

    bing = (await logged_in.get("/api/seo", params={"engine": "bing", "period": "last_28_days"})).json()
    report = bing["sites"][0]
    assert report["totals"]["position"] is None and report["queries"] == []
    assert len(report["crawl"]) == 28
    assert all(day["indexed"] is not None for day in report["crawl"])
    assert report["pages"] and all(p["position"] is not None for p in report["pages"])

    # 比べる期間に数字が1日もなければ、比べられない（compare_clicks は null）
    past = (await logged_in.get("/api/seo", params={"compare": "previous_year"})).json()["sites"][0]
    assert past["compare_totals"] == {"clicks": 0, "impressions": 0, "position": None}
    assert all(q["compare_clicks"] is None for q in past["queries"])


async def test_seo_report_is_per_tenant(app: FastAPI, logged_in: AsyncClient, database_url: str) -> None:
    await linked_site(logged_in)
    _query(database_url, "INSERT INTO tenants (id, name) VALUES (2, '別の顧客')")
    _query(database_url, "UPDATE users SET tenant_id = 2")
    assert (await logged_in.get("/api/seo")).json()["sites"] == []


async def test_seo_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/seo")).status_code == 401


# --- サイトマップとインデックスの目安 --------------------------------------------------------


class Pages:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    async def fetch(self, url: str) -> bytes:
        return self.files[url]


async def test_sitemap_paths_follow_index_and_gzip() -> None:
    import gzip

    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    files = {
        "https://a.example/sitemap_index.xml": f"<sitemapindex {ns}><sitemap><loc>https://a.example/post.xml.gz</loc></sitemap>"
        f"<sitemap><loc> https://a.example/page.xml </loc></sitemap></sitemapindex>".encode(),
        "https://a.example/post.xml.gz": gzip.compress(
            f"<urlset {ns}><url><loc>https://a.example/%E5%80%89%E5%BA%AB/</loc></url></urlset>".encode()
        ),
        "https://a.example/page.xml": f"<urlset {ns}><url><loc>https://a.example/</loc></url>"
        f"<url><loc>https://www.a.example/about/?x=1</loc></url></urlset>".encode(),
    }
    assert await sitemap_paths(Pages(files), ["https://a.example/sitemap_index.xml"]) == {"/", "/about/", "/倉庫/"}


async def test_sitemap_paths_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from glance.sync import sitemap

    monkeypatch.setattr(sitemap, "MAX_URLS", 1)
    with pytest.raises(ValueError, match="URL が 1 を超えました"):
        await sitemap_paths(FakeSitemapFetcher(), ["https://a.example/sitemap_index.xml"])


class NoSitemaps(FakeGa4Client):
    async def gsc_sitemaps(self, site_url: str) -> list[str]:
        return []


async def test_seo_report_index(app: FastAPI, logged_in: AsyncClient, database_url: str) -> None:
    site = await linked_site(logged_in)
    await syncer(app, date.today()).run({"gsc"})
    # 索引→2つのサイトマップから6ページ。パスにそろえる（エンコードを解除する）
    assert len(_query(database_url, "SELECT path FROM sitemap_urls WHERE site_id = %s", (site["id"],))) == 6
    index = (await logged_in.get("/api/seo", params={"period": "last_7_days"})).json()["sites"][0]["index"]
    assert index["sitemap_urls"] == 6
    assert index["sitemap_checked_at"] == date.today().isoformat()
    # 検索に出ているのは4ページ（ダミーの Search Console のページ）で、どれもサイトマップにある
    assert (index["indexed"], index["pages_shown"]) == (4, 4)
    assert len(index["daily"]) == 7 and all(d["pages"] == 4 for d in index["daily"])
    # Bing は、同じサイトマップの URL 数と、Bing のインデックス数（期間の最後の日）
    await syncer(app, date.today()).run({"bing"})
    bing = (await logged_in.get("/api/seo", params={"engine": "bing"})).json()["sites"][0]
    assert bing["index"]["sitemap_urls"] == 6
    assert bing["index"]["indexed"] == next(d["indexed"] for d in reversed(bing["crawl"]) if d["indexed"] is not None)
    assert (bing["index"]["pages_shown"], bing["index"]["daily"]) == (None, None)


@pytest.mark.parametrize("ga4", [NoSitemaps(latency=(0, 0))])
async def test_sitemap_missing_is_logged(app: FastAPI, logged_in: AsyncClient, database_url: str) -> None:
    await linked_site(logged_in)
    outcomes = await syncer(app, date.today()).run({"gsc"})
    [failed] = [o for o in outcomes if o.error]
    assert failed.table == "sitemap_urls" and "サイトマップが登録されていません" in failed.error
    index = (await logged_in.get("/api/seo")).json()["sites"][0]["index"]
    # サイトマップを読めていなければ、URL 数とサイトマップにあるページ数は出さない（検索に出たページ数は出す）
    assert (index["sitemap_urls"], index["indexed"], index["pages_shown"] > 0) == (None, None, True)

"""SEO の画面の期間の計算と、デモ用の API。"""

from datetime import date

import pytest
from httpx import AsyncClient

from glance.seo.periods import PeriodError, Range, resolve_compare, resolve_period

UNTIL = date(2026, 11, 23)


def test_periods() -> None:
    assert resolve_period("last_7_days", UNTIL) == Range(date(2026, 11, 17), UNTIL)
    assert resolve_period("last_28_days", UNTIL) == Range(date(2026, 10, 27), UNTIL)
    assert resolve_period("this_month", UNTIL) == Range(date(2026, 11, 1), UNTIL)
    assert resolve_period("last_month", UNTIL) == Range(date(2026, 10, 1), date(2026, 10, 31))
    # 指定の終わりは、データがある最終日まで
    assert resolve_period("custom", UNTIL, date(2026, 11, 20), date(2026, 11, 30)) == Range(date(2026, 11, 20), UNTIL)
    with pytest.raises(PeriodError):
        resolve_period("custom", UNTIL)
    with pytest.raises(PeriodError):
        resolve_period("custom", UNTIL, date(2026, 11, 10), date(2026, 11, 1))


def test_compare() -> None:
    current = resolve_period("last_28_days", UNTIL)
    assert resolve_compare("previous_period", "last_28_days", current) == Range(date(2026, 9, 29), date(2026, 10, 26))
    assert resolve_compare("previous_year", "last_28_days", current) == Range(date(2025, 10, 27), date(2025, 11, 23))
    assert resolve_compare("none", "last_28_days", current) is None
    # 今月・先月は、前の月の全体と比べる
    this_month = resolve_period("this_month", UNTIL)
    assert resolve_compare("previous_period", "this_month", this_month) == Range(date(2026, 10, 1), date(2026, 10, 31))
    # 2/29 の前年は 2/28
    assert resolve_compare("previous_year", "custom", Range(date(2028, 2, 29), date(2028, 2, 29))) == Range(
        date(2027, 2, 28), date(2027, 2, 28)
    )


async def test_demo_google(client: AsyncClient) -> None:
    response = await client.get("/api/demo/seo?engine=google&period=last_28_days&compare=previous_period")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "google"
    assert body["period"]["label"] == "直近28日"
    assert body["compare"] is not None
    site = body["sites"][0]
    assert site["name"] == "デモサイト A"
    assert len(site["daily"]) == 28 and len(site["compare_daily"]) == 28
    assert site["totals"]["clicks"] == sum(d["clicks"] for d in site["daily"])
    assert site["totals"]["position"] is not None
    assert 0 < len(site["queries"]) <= 100 and "compare_clicks" in site["queries"][0]
    assert [q["clicks"] for q in site["queries"]] == sorted((q["clicks"] for q in site["queries"]), reverse=True)
    assert site["pages"][0]["path"].startswith("/")
    assert site["crawl"] is None
    # インデックスの目安（本物と同じ形）
    index = site["index"]
    assert set(index) == {"sitemap_urls", "sitemap_checked_at", "indexed", "pages_shown", "daily"}
    assert 0 < index["indexed"] <= index["sitemap_urls"] and index["pages_shown"] >= index["indexed"]
    assert len(index["daily"]) == 28
    # 同じ条件なら同じ数字
    again = (await client.get("/api/demo/seo?engine=google&period=last_28_days&compare=previous_period")).json()
    assert again["sites"][0]["totals"] == site["totals"]


async def test_demo_bing(client: AsyncClient) -> None:
    body = (await client.get("/api/demo/seo?engine=bing&period=last_7_days&compare=none")).json()
    site = body["sites"][0]
    assert body["compare"] is None and site["compare_totals"] is None
    assert site["totals"]["position"] is None  # Bing の日ごとの数字に掲載順位はない
    assert site["queries"] == []  # Bing のクエリは今は取らない
    assert len(site["crawl"]) == 7 and {"crawled", "indexed", "errors"} <= set(site["crawl"][0])
    assert site["pages"][0]["compare_clicks"] is None
    # Bing のインデックスは、クロールの数字の期間の最後の日のインデックス数
    assert site["index"]["indexed"] == site["crawl"][-1]["indexed"]
    assert (site["index"]["pages_shown"], site["index"]["daily"]) == (None, None)


async def test_demo_rejects_bad_period(client: AsyncClient) -> None:
    response = await client.get("/api/demo/seo?period=custom&start=2026-11-10&end=2026-11-01")
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_period"
    assert (await client.get("/api/demo/seo?engine=yahoo")).status_code == 422

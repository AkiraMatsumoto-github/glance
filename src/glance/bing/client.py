"""Bing Webmaster API の呼び出しの入口（data_sources.md §4）。

認証は API キー。キーはクエリ文字列で送る仕様なので、URL をログやエラーの文に出さない
（httpx のログは glance/logs.py で抑える）。
"""

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import httpx

API_URL = "https://ssl.bing.com/webmaster/api.svc/json"


class BingKeyInvalid(Exception):
    """API キーが使えない（間違い・取り消し済み）。"""


class BingUnavailable(Exception):
    """Bing の API に届かない、または Bing 側のエラー。"""


class BingClient(Protocol):
    async def list_sites(self, api_key: str) -> list[str]:
        """キーで見られる（確認済みの）サイトの URL（GetUserSites）。"""
        ...

    async def stats(self, api_key: str, method: str, site_url: str) -> list[dict[str, Any]]:
        """サイトの数字（GetRankAndTrafficStats・GetPageStats・GetCrawlStats）。API が返した1件ずつ、そのまま。"""
        ...


class RealBingClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport  # テストで差し替える

    async def _get(self, method: str, api_key: str, **params: str) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=60, transport=self._transport) as http:
                response = await http.get(f"{API_URL}/{method}", params={**params, "apikey": api_key})
        except httpx.HTTPError:
            # 元の例外はキーを含む URL を持つので、つなげない
            raise BingUnavailable() from None
        if response.status_code in (400, 401, 403):
            raise BingKeyInvalid()
        if response.status_code != 200:
            raise BingUnavailable()
        return response.json().get("d") or []

    async def list_sites(self, api_key: str) -> list[str]:
        sites = await self._get("GetUserSites", api_key)
        return sorted(site["Url"] for site in sites if site.get("IsVerified", True))

    async def stats(self, api_key: str, method: str, site_url: str) -> list[dict[str, Any]]:
        return await self._get(method, api_key, siteUrl=site_url)


# 手元（GLANCE_FAKE_GOOGLE=1）とテストで使うダミー。「bad」で始まるキーは使えないキーとして扱う
FAKE_BING_SITES = [
    "https://conshift.example/",
    "https://finshift.example/",
    "https://leadhub.example/",
    "https://techshift.example/",
    "https://www.logishift.example/",
]


def _bing_date(day: date) -> str:
    # Bing の日付の形（太平洋時間の0時を、ミリ秒とずれで書く）
    moment = datetime(day.year, day.month, day.day, 8, tzinfo=UTC)
    return f"/Date({int(moment.timestamp() * 1000)}-0800)/"


class FakeBingClient:
    def __init__(self, sites_by_key: dict[str, list[str]] | None = None, today: date | None = None) -> None:
        self._sites_by_key = sites_by_key
        self._today = today

    async def stats(self, api_key: str, method: str, site_url: str) -> list[dict[str, Any]]:
        await self.list_sites(api_key)
        # 日次は98日分、ページ別は13週分（data_sources.md §4）。数字はサイトと日付から決まる
        today = self._today or date.today()
        if method == "GetPageStats":
            weeks = [today - timedelta(days=today.weekday() + 7 * (i + 1)) for i in range(13)]
            return [
                {
                    "Date": _bing_date(week),
                    "Query": f"{site_url.rstrip('/')}{path}",
                    "Clicks": (r := random.Random(f"{site_url}:{week}:{path}")).randint(0, 30),
                    "Impressions": r.randint(30, 600),
                    "AvgClickPosition": round(r.uniform(1, 10), 1),
                    "AvgImpressionPosition": round(r.uniform(1, 20), 1),
                }
                for week in weeks
                for path in ["/", "/glossary/wms/", "/news/2024-problem/"]
            ]
        rows = []
        for i in range(1, 99):
            day = today - timedelta(days=i)
            r = random.Random(f"{site_url}:{method}:{day}")
            if method == "GetRankAndTrafficStats":
                rows.append({"Date": _bing_date(day), "Clicks": r.randint(0, 40), "Impressions": r.randint(100, 900)})
            else:
                rows.append(
                    {
                        "Date": _bing_date(day),
                        "CrawledPages": r.randint(50, 400),
                        "CrawlErrors": r.choice([0, 0, 1, 3]),
                        "InIndex": 1200 + i,
                        "InLinks": 300 + i // 7,
                    }
                )
        return rows

    async def list_sites(self, api_key: str) -> list[str]:
        if self._sites_by_key is not None:
            if api_key not in self._sites_by_key:
                raise BingKeyInvalid()
            return self._sites_by_key[api_key]
        if api_key.startswith("bad"):
            raise BingKeyInvalid()
        return list(FAKE_BING_SITES)

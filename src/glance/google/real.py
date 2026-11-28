"""本物の GA4（Data API・Admin API）と Search Console のサイトの一覧。ログインした利用者の更新トークンで呼ぶ
（data_sources.md §2・§3・§5）。"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

import google.auth.transport.requests
from google.analytics.admin_v1beta import AnalyticsAdminServiceAsyncClient
from google.analytics.data_v1beta import BetaAnalyticsDataAsyncClient, Dimension, Metric, OrderBy, RunRealtimeReportRequest
from google.api_core import exceptions as api_errors
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from glance.auth.google import SCOPES, TOKEN_URI
from glance.google.ga4 import (
    AccountSummary,
    BreakdownDimension,
    BreakdownRow,
    EventRow,
    Ga4PermissionDenied,
    Ga4QuotaExceeded,
    GscApiDisabled,
    GscRow,
    MinuteRow,
    PageRow,
    PropertyInfo,
    PropertySummary,
    ReauthRequired,
    Totals,
)

PV, UU, KEY_EVENTS, EVENTS = "screenPageViews", "activeUsers", "keyEvents", "eventCount"

GSC_SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"


def make_credentials(refresh_token: str, client_id: str, client_secret: str) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )


def _int(value: str) -> int:
    return int(float(value or 0))


class RealGa4Client:
    def __init__(
        self,
        credentials: Credentials,
        data_client: Any | None = None,
        admin_client: Any | None = None,
        gsc_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._data = data_client or BetaAnalyticsDataAsyncClient(credentials=credentials)
        self._admin = admin_client or AnalyticsAdminServiceAsyncClient(credentials=credentials)
        self._gsc_transport = gsc_transport  # テストで差し替える
        self._refresh_lock = asyncio.Lock()

    async def _ensure_token(self) -> None:
        # アクセストークン（約1時間）が切れていたら、呼ぶ前に取り直す。
        # 更新トークンが失効していると RefreshError（invalid_grant）になるので、ログインし直してもらう
        async with self._refresh_lock:
            if self._credentials.valid:
                return
            try:
                await asyncio.to_thread(self._credentials.refresh, google.auth.transport.requests.Request())
            except RefreshError as e:
                raise ReauthRequired() from e

    async def _call[T](self, fn: Callable[[], Awaitable[T]]) -> T:
        await self._ensure_token()
        try:
            return await fn()
        except api_errors.Unauthenticated as e:
            raise ReauthRequired() from e
        except (api_errors.PermissionDenied, api_errors.NotFound) as e:
            raise Ga4PermissionDenied() from e
        except api_errors.ResourceExhausted as e:
            raise Ga4QuotaExceeded() from e

    # Admin API

    async def list_account_summaries(self) -> list[AccountSummary]:
        async def run() -> list[AccountSummary]:
            pager = await self._admin.list_account_summaries()
            result = []
            async for summary in pager:
                result.append(
                    AccountSummary(
                        account_id=summary.account.split("/")[-1],
                        name=summary.display_name,
                        properties=[
                            PropertySummary(p.property.split("/")[-1], p.display_name)
                            for p in summary.property_summaries
                        ],
                    )
                )
            return result

        return await self._call(run)

    async def get_property(self, property_id: str) -> PropertyInfo:
        async def run() -> PropertyInfo:
            prop = await self._admin.get_property(name=f"properties/{property_id}")
            return PropertyInfo(property_id=property_id, name=prop.display_name, time_zone=prop.time_zone)

        return await self._call(run)

    async def web_stream_hosts(self, property_id: str) -> list[str]:
        async def run() -> list[str]:
            pager = await self._admin.list_data_streams(parent=f"properties/{property_id}")
            hosts = []
            async for stream in pager:
                uri = stream.web_stream_data.default_uri
                host = urlsplit(uri if "://" in uri else f"https://{uri}").hostname if uri else None
                if host:
                    hosts.append(host)
            return hosts

        return await self._call(run)

    # Search Console API

    async def _gsc(self, method: str, url: str, body: dict[str, Any] | None = None) -> Any:
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=60, transport=self._gsc_transport) as http:
            response = await http.request(
                method, url, json=body, headers={"Authorization": f"Bearer {self._credentials.token}"}
            )
        if response.status_code < 400:
            return response.json()
        text = response.text
        try:
            message = str(response.json().get("error", {}).get("message", ""))[:300]
        except ValueError:
            message = text[:300]
        if response.status_code == 401:
            raise ReauthRequired()
        # 上限（1分あたりの回数など）は、429 のほか 403 でも返る
        if response.status_code == 429 or any(
            word in text for word in ("rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "RATE_LIMIT_EXCEEDED")
        ):
            raise Ga4QuotaExceeded(message)
        if response.status_code == 403:
            if "SERVICE_DISABLED" in text or "accessNotConfigured" in text:
                raise GscApiDisabled(message)
            if "insufficient" in text.lower():
                # Search Console を読む許可をもらっていない。ログインし直して許可してもらう
                raise ReauthRequired()
            raise Ga4PermissionDenied(message)
        response.raise_for_status()
        return response.json()

    async def list_gsc_sites(self) -> list[str]:
        entries = (await self._gsc("GET", GSC_SITES_URL)).get("siteEntry", [])
        return sorted(e["siteUrl"] for e in entries if e.get("permissionLevel") != "siteUnverifiedUser")

    async def gsc_sitemaps(self, site_url: str) -> list[str]:
        result = await self._gsc("GET", f"{GSC_SITES_URL}/{quote(site_url, safe='')}/sitemaps")
        return [s["path"] for s in result.get("sitemap", [])]

    async def gsc_search_analytics(
        self, site_url: str, start: date, end: date, dimensions: list[str], start_row: int, row_limit: int
    ) -> list[GscRow]:
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dimensions,
            "type": "web",
            "dataState": "final",
            "rowLimit": row_limit,
            "startRow": start_row,
        }
        result = await self._gsc("POST", f"{GSC_SITES_URL}/{quote(site_url, safe='')}/searchAnalytics/query", body)
        return [
            GscRow(
                keys=row["keys"],
                clicks=round(row["clicks"]),
                impressions=round(row["impressions"]),
                position=row["position"],
            )
            for row in result.get("rows", [])
        ]

    # Data API（リアルタイム）

    async def _realtime(
        self,
        property_id: str,
        metrics: list[str],
        dimension: str | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> Any:
        request = RunRealtimeReportRequest(
            property=f"properties/{property_id}",
            metrics=[Metric(name=m) for m in metrics],
            dimensions=[Dimension(name=dimension)] if dimension else [],
            limit=limit or 0,
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_by), desc=True)] if order_by else [],
        )
        return await self._call(lambda: self._data.run_realtime_report(request=request))

    async def realtime_totals(self, property_id: str) -> Totals:
        response = await self._realtime(property_id, [PV, UU, KEY_EVENTS])
        if not response.rows:
            return Totals(page_views=0, active_users=0, key_events=0)
        values = [_int(v.value) for v in response.rows[0].metric_values]
        return Totals(page_views=values[0], active_users=values[1], key_events=values[2])

    async def realtime_per_minute(self, property_id: str) -> list[MinuteRow]:
        response = await self._realtime(property_id, [PV, UU], dimension="minutesAgo")
        return [
            MinuteRow(
                minutes_ago=_int(row.dimension_values[0].value),
                page_views=_int(row.metric_values[0].value),
                active_users=_int(row.metric_values[1].value),
            )
            for row in response.rows
        ]

    async def realtime_top_pages(self, property_id: str, limit: int) -> list[PageRow]:
        response = await self._realtime(property_id, [PV, UU], dimension="unifiedScreenName", limit=limit, order_by=PV)
        return [
            PageRow(
                title=row.dimension_values[0].value,
                page_views=_int(row.metric_values[0].value),
                active_users=_int(row.metric_values[1].value),
            )
            for row in response.rows
        ]

    async def realtime_breakdown(
        self, property_id: str, dimension: BreakdownDimension, limit: int
    ) -> list[BreakdownRow]:
        response = await self._realtime(property_id, [UU], dimension=dimension, limit=limit, order_by=UU)
        return [
            BreakdownRow(key=row.dimension_values[0].value, active_users=_int(row.metric_values[0].value))
            for row in response.rows
        ]

    async def realtime_events(self, property_id: str, limit: int) -> list[EventRow]:
        response = await self._realtime(property_id, [EVENTS], dimension="eventName", limit=limit, order_by=EVENTS)
        return [
            EventRow(name=row.dimension_values[0].value, event_count=_int(row.metric_values[0].value))
            for row in response.rows
        ]

"""本物の GA4（Data API・Admin API）。ログインした利用者の更新トークンで呼ぶ（data_sources.md §2・§5）。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

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
    MinuteRow,
    PageRow,
    PropertyInfo,
    PropertySummary,
    ReauthRequired,
    Totals,
)

PV, UU, KEY_EVENTS, EVENTS = "screenPageViews", "activeUsers", "keyEvents", "eventCount"


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
    ) -> None:
        self._credentials = credentials
        self._data = data_client or BetaAnalyticsDataAsyncClient(credentials=credentials)
        self._admin = admin_client or AnalyticsAdminServiceAsyncClient(credentials=credentials)
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

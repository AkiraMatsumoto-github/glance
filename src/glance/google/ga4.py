"""GA4 の呼び出しの入口。

本物（Data API・Admin API）は2番目の段階で Google ログインをつないでから作る。
それまでは、手元でフェイク（glance.google.fake）だけを使う。
"""

from dataclasses import dataclass
from typing import Literal, Protocol


class ReauthRequired(Exception):
    """更新トークンが失効した。ログインし直しが要る。"""


class Ga4PermissionDenied(Exception):
    """プロパティを見る権限がない。"""


class Ga4QuotaExceeded(Exception):
    """GA4 の API の上限に当たった。"""


class Ga4NotConfigured(Exception):
    """Google の接続がまだ設定されていない。"""


@dataclass(frozen=True)
class PropertySummary:
    property_id: str
    name: str


@dataclass(frozen=True)
class AccountSummary:
    account_id: str
    name: str
    properties: list[PropertySummary]


@dataclass(frozen=True)
class PropertyInfo:
    property_id: str
    name: str
    time_zone: str


@dataclass(frozen=True)
class Totals:
    page_views: int
    active_users: int
    key_events: int


@dataclass(frozen=True)
class MinuteRow:
    minutes_ago: int
    page_views: int
    active_users: int


@dataclass(frozen=True)
class PageRow:
    title: str
    page_views: int
    active_users: int


# 内訳に使う軸（data_sources.md §5 の4回目・5回目）
BreakdownDimension = Literal["deviceCategory", "countryId"]


@dataclass(frozen=True)
class BreakdownRow:
    key: str  # deviceCategory の値（mobile など）、または countryId（ISO 3166-1 の2文字。JP など）
    page_views: int
    active_users: int


class Ga4Client(Protocol):
    """1人の利用者の権限で GA4 を呼ぶ。"""

    async def list_account_summaries(self) -> list[AccountSummary]:
        """見られるアカウントとプロパティの一覧（Admin API の accountSummaries.list）。"""
        ...

    async def get_property(self, property_id: str) -> PropertyInfo:
        """プロパティの名前とタイムゾーン（Admin API の properties.get）。"""
        ...

    async def realtime_totals(self, property_id: str) -> Totals:
        """直近30分の合計（軸なし。data_sources.md §5 の1回目）。"""
        ...

    async def realtime_per_minute(self, property_id: str) -> list[MinuteRow]:
        """分ごとの PV・UU（minutesAgo。2回目）。値のない分は含まれない。"""
        ...

    async def realtime_top_pages(self, property_id: str, limit: int) -> list[PageRow]:
        """PV の多いページ（unifiedScreenName。3回目）。"""
        ...

    async def realtime_breakdown(
        self, property_id: str, dimension: BreakdownDimension, limit: int
    ) -> list[BreakdownRow]:
        """軸ごとの PV・UU（deviceCategory が4回目、countryId が5回目）。PV の多い順。"""
        ...

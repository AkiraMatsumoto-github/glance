"""SEO の画面の API（GET /api/seo・GET /api/demo/seo）の応答の形（technical_design.md §6.3・§6.5）。

本物（glance/seo/service.py）とデモ（glance/seo/demo.py）で同じ形にし、画面は取り元だけを変えて同じ部品を使う。
"""

import datetime as dt

from pydantic import BaseModel

from glance.seo.periods import Engine, Range

TOP = 100  # クエリ・ページは、サイトごとにクリックの多い順に100件まで


class SeoTotals(BaseModel):
    clicks: int
    impressions: int
    position: float | None  # 表示回数の重みつき平均。Bing は日ごとの掲載順位が無いので None


class SeoDay(SeoTotals):
    date: dt.date


class SeoItem(BaseModel):
    clicks: int
    impressions: int
    position: float | None  # 表示回数の重みつき平均（Bing の週で順位の分からないものは重みに入れない）
    # 比べる期間のクリック。比べないとき・比べる期間にそのサイトの数字が1日も無いときは None。あれば、無いものは 0
    compare_clicks: int | None


class SeoQuery(SeoItem):
    query: str


class SeoPage(SeoItem):
    title: str | None  # 本物はタイトルを持っていない（GA4 の取り込みを作るまで None。画面はパスを出す）
    path: str


class CrawlDay(BaseModel):
    """Bing のクロールの数字。数字のない日は None（インデックス数は在庫なので 0 にしない）。"""

    date: dt.date
    crawled: int | None
    indexed: int | None
    errors: int | None


class IndexDay(BaseModel):
    date: dt.date
    pages: int  # その日に検索に出た（imp 1回以上の）ページ数


class SeoIndex(BaseModel):
    """インデックスの目安（screen_design.md §7）。サイトマップの URL 数と並べる。

    indexed は、Google は期間中に検索に出たページのうちサイトマップにあるものの数（サイトマップを読めていなければ None）、
    Bing は Bing のインデックス数（期間の中で数字のある最後の日）。pages_shown と daily は Google だけ。
    """

    sitemap_urls: int | None  # まだ読めていなければ None
    sitemap_checked_at: dt.date | None
    indexed: int | None
    pages_shown: int | None  # サイトマップに無いページも含めた、検索に出たページ数
    daily: list[IndexDay] | None


class SeoSite(BaseModel):
    site_id: int
    name: str
    totals: SeoTotals
    compare_totals: SeoTotals | None
    daily: list[SeoDay]  # 期間の全部の日（比べる期間と、何日目かでそろえる）
    compare_daily: list[SeoDay] | None
    queries: list[SeoQuery]  # Bing のクエリは今は取らないので空
    pages: list[SeoPage]
    crawl: list[CrawlDay] | None  # Bing だけ
    index: SeoIndex


class SeoSpan(BaseModel):
    start: dt.date
    end: dt.date

    @classmethod
    def of(cls, r: Range) -> "SeoSpan":
        return cls(start=r.start, end=r.end)


class Seo(BaseModel):
    engine: Engine
    period: SeoSpan
    compare: SeoSpan | None
    data_until: dt.date | None  # 取り込んだ数字がある最終日。まだ何も取り込んでいなければ None（デモはいつもある）
    sites: list[SeoSite]

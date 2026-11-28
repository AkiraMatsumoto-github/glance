"""SEO の画面の数字を、取り込んだ表から集計する（GET /api/seo。technical_design.md §6.3・§6.5）。

応答の形（glance/seo/schemas.py）はデモ（glance/seo/demo.py）と同じ。違いは次のとおり。
- サイトは、その検索エンジン（Search Console か Bing）を紐づけたものだけ。
- data_until は、取り込んだ数字がある最終日。まだ何も取り込んでいなければ null（期間は既定の最終日で決める）。
- ページのタイトルは持っていない（GA4 の取り込みを作るまで null。画面はパスを出す）。
- 比べる期間に、そのサイトの数字が1日もなければ compare_clicks は null。あれば、無いクエリ・ページは 0。
- index（インデックスの目安）。サイトマップの URL 数と、Google は期間中に検索に出たページ（imp 1回以上）、Bing はインデックス数。
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import and_, case, func, null, select
from sqlalchemy.ext.asyncio import AsyncSession

from glance.db.models import (
    BingCrawlDaily,
    BingPageWeekly,
    BingSiteDaily,
    Connection,
    GscPage,
    GscQueryPage,
    GscSite,
    Site,
    SitemapUrl,
    SyncRun,
)
from glance.seo.periods import CompareName, Engine, PeriodName, Range, default_data_until, resolve_compare, resolve_period
from glance.seo.schemas import (
    TOP,
    CrawlDay,
    IndexDay,
    Seo,
    SeoDay,
    SeoIndex,
    SeoPage,
    SeoQuery,
    SeoSite,
    SeoSpan,
    SeoTotals,
)


@dataclass(frozen=True)
class _Found:
    """取り込んだ表の、サイトの1日分の数字。weighted は掲載順位×表示回数の和（Bing は None）。"""

    clicks: int
    impressions: int
    weighted: float | None


_NOTHING = _Found(0, 0, None)


def _position(weighted: float | None, impressions: int) -> float | None:
    return round(weighted / impressions, 1) if weighted is not None and impressions else None


async def _daily(db: AsyncSession, engine: Engine, site_ids: list[int], r: Range) -> dict[int, dict[date, _Found]]:
    if engine == "google":
        query = select(
            GscSite.site_id, GscSite.date, func.sum(GscSite.clicks), func.sum(GscSite.impressions),
            func.sum(GscSite.position_weighted),
        ).where(GscSite.site_id.in_(site_ids), GscSite.date.between(r.start, r.end)).group_by(GscSite.site_id, GscSite.date)
    else:
        query = select(
            BingSiteDaily.site_id, BingSiteDaily.date, BingSiteDaily.clicks, BingSiteDaily.impressions, null()
        ).where(BingSiteDaily.site_id.in_(site_ids), BingSiteDaily.date.between(r.start, r.end))
    result: dict[int, dict[date, _Found]] = {}
    for site_id, day, clicks, impressions, weighted in await db.execute(query):
        result.setdefault(site_id, {})[day] = _Found(
            int(clicks), int(impressions), float(weighted) if weighted is not None else None
        )
    return result


def _daily_rows(found: dict[date, _Found], r: Range) -> list[SeoDay]:
    # 期間の全部の日を並べる（数字のない日は 0）。比べる期間と、何日目かでそろえるため
    rows = []
    for day in r.dates():
        value = found.get(day, _NOTHING)
        rows.append(
            SeoDay(
                date=day,
                clicks=value.clicks,
                impressions=value.impressions,
                position=_position(value.weighted, value.impressions),
            )
        )
    return rows


def _totals(found: dict[date, _Found], engine: Engine) -> SeoTotals:
    clicks = sum(v.clicks for v in found.values())
    impressions = sum(v.impressions for v in found.values())
    weighted = sum(v.weighted or 0 for v in found.values()) if engine == "google" else None
    return SeoTotals(clicks=clicks, impressions=impressions, position=_position(weighted, impressions))


async def _ranking(
    db: AsyncSession, engine: Engine, kind: str, site_id: int, current: Range, previous: Range | None,
    compare_has_data: bool,
) -> list[SeoQuery | SeoPage]:
    """クエリかページの上位100件と、比べる期間のクリック。"""
    if engine == "google":
        model = GscQueryPage if kind == "query" else GscPage
        key = GscQueryPage.query if kind == "query" else GscPage.page
        day = model.date
        weighted = func.sum(model.position_weighted)
        weight = func.sum(model.impressions)
    else:
        model, key, day = BingPageWeekly, BingPageWeekly.page, BingPageWeekly.week
        weighted = func.sum(BingPageWeekly.position * BingPageWeekly.impressions)
        # 順位が分からない週の表示回数は、平均の重みに入れない（入れると順位が良く出すぎる）
        weight = func.sum(case((BingPageWeekly.position.is_not(None), BingPageWeekly.impressions), else_=0))

    def in_range(r: Range) -> Any:
        return (model.site_id == site_id) & day.between(r.start, r.end)

    clicks, impressions = func.sum(model.clicks), func.sum(model.impressions)
    top = (
        await db.execute(
            select(key, clicks, impressions, weighted, weight)
            .where(in_range(current))
            .group_by(key)
            .order_by(clicks.desc(), impressions.desc(), key)
            .limit(TOP)
        )
    ).all()
    # 比べる期間に、そのサイトの数字が1日もなければ比べない（null）。あれば、比べる期間に無いものは 0
    compared = previous is not None and compare_has_data
    before: dict[str, int] = {}
    if previous is not None and compared and top:
        names = [row[0] for row in top]
        found = await db.execute(select(key, clicks).where(in_range(previous), key.in_(names)).group_by(key))
        before = {name: int(value) for name, value in found}
    result: list[SeoQuery | SeoPage] = []
    for name, c, i, w, n in top:
        metrics: dict[str, Any] = {
            "clicks": int(c),
            "impressions": int(i),
            "position": _position(float(w) if w is not None else None, int(n or 0)),
            "compare_clicks": before.get(name, 0) if compared else None,
        }
        result.append(SeoQuery(query=name, **metrics) if kind == "query" else SeoPage(title=None, path=name, **metrics))
    return result


async def _crawl(db: AsyncSession, site_id: int, r: Range) -> list[CrawlDay]:
    found = {
        row.date: row
        for row in await db.scalars(
            select(BingCrawlDaily).where(BingCrawlDaily.site_id == site_id, BingCrawlDaily.date.between(r.start, r.end))
        )
    }
    # 全部の日を並べる。数字のない日は null（インデックス数は在庫なので 0 にしない）
    return [
        CrawlDay(
            date=day,
            crawled=found[day].crawled if day in found else None,
            indexed=found[day].indexed if day in found else None,
            errors=found[day].crawl_errors if day in found else None,
        )
        for day in r.dates()
    ]


async def _sitemap(db: AsyncSession, site_id: int) -> tuple[int | None, date | None]:
    """サイトマップの URL 数と、読んだ日。まだ読めていなければ (None, None)。"""
    checked = await db.scalar(
        select(func.max(SyncRun.end_date)).where(SyncRun.site_id == site_id, SyncRun.table_name == "sitemap_urls", SyncRun.ok)
    )
    if checked is None:
        return None, None
    return await db.scalar(select(func.count()).where(SitemapUrl.site_id == site_id)), checked


async def _index(db: AsyncSession, engine: Engine, site_id: int, r: Range) -> SeoIndex:
    """インデックスの目安。サイトマップの URL 数と並べる（screen_design.md §7）。

    Google: Search Console の API ではインデックス登録の数を取れないので、期間中に検索に1回でも出た（imp 1回以上の）
    ページのうち、サイトマップにあるものの数。出ていないページは、インデックスされていないか順位が低いかで、区別できない。
    Bing: Bing のインデックス数（在庫）の、期間の中で数字のある最後の日の値。
    """
    sitemap_urls, checked = await _sitemap(db, site_id)
    if engine == "bing":
        latest = await db.scalar(
            select(BingCrawlDaily.indexed)
            .where(BingCrawlDaily.site_id == site_id, BingCrawlDaily.date.between(r.start, r.end))
            .order_by(BingCrawlDaily.date.desc())
            .limit(1)
        )
        return SeoIndex(sitemap_urls=sitemap_urls, sitemap_checked_at=checked, indexed=latest, pages_shown=None, daily=None)

    shown = and_(GscPage.site_id == site_id, GscPage.date.between(r.start, r.end), GscPage.impressions > 0)
    in_sitemap = select(SitemapUrl.path).where(SitemapUrl.site_id == site_id)
    pages = func.count(func.distinct(GscPage.page))
    daily = dict((await db.execute(select(GscPage.date, pages).where(shown).group_by(GscPage.date))).all())
    return SeoIndex(
        sitemap_urls=sitemap_urls,
        sitemap_checked_at=checked,
        # サイトマップをまだ読めていなければ、サイトマップにあるかは分からない
        indexed=await db.scalar(select(pages).where(shown, GscPage.page.in_(in_sitemap))) if checked else None,
        pages_shown=await db.scalar(select(pages).where(shown)) or 0,
        daily=[IndexDay(date=day, pages=daily.get(day, 0)) for day in r.dates()],
    )


async def seo_report(
    db: AsyncSession,
    tenant_id: int,
    engine: Engine,
    period: PeriodName,
    compare: CompareName,
    today: date,
    start: date | None = None,
    end: date | None = None,
) -> Seo:
    # 出すのは、その検索エンジンを紐づけた（接続設定の行がある）サイトだけ
    source = "gsc" if engine == "google" else "bing"
    sites = list(
        await db.scalars(
            select(Site)
            .join(Connection, (Connection.site_id == Site.id) & (Connection.source == source))
            .where(Site.tenant_id == tenant_id)
            .order_by(Site.sort_order, Site.id)
        )
    )
    site_ids = [s.id for s in sites]
    daily_model = GscSite if engine == "google" else BingSiteDaily
    latest = (
        await db.scalar(select(func.max(daily_model.date)).where(daily_model.site_id.in_(site_ids))) if site_ids else None
    )
    current = resolve_period(period, latest or default_data_until(engine, today), start, end)
    previous = resolve_compare(compare, period, current)
    daily = await _daily(db, engine, site_ids, current) if site_ids else {}
    before = await _daily(db, engine, site_ids, previous) if site_ids and previous else {}

    result_sites = []
    for site in sites:
        found = daily.get(site.id, {})
        found_before = before.get(site.id, {})
        compare_has_data = bool(found_before)
        result_sites.append(
            SeoSite(
                site_id=site.id,
                name=site.name,
                totals=_totals(found, engine),
                compare_totals=_totals(found_before, engine) if previous else None,
                daily=_daily_rows(found, current),
                compare_daily=_daily_rows(found_before, previous) if previous else None,
                queries=await _ranking(db, engine, "query", site.id, current, previous, compare_has_data)
                if engine == "google"
                else [],
                pages=await _ranking(db, engine, "page", site.id, current, previous, compare_has_data),
                crawl=await _crawl(db, site.id, current) if engine == "bing" else None,
                index=await _index(db, engine, site.id, current),
            )
        )
    return Seo(
        engine=engine,
        period=SeoSpan.of(current),
        compare=SeoSpan.of(previous) if previous else None,
        data_until=latest,
        sites=result_sites,
    )

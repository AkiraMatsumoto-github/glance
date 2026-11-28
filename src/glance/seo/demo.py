"""SEO の画面のデモ用のダミーの数字（screen_design.md §6・§7、technical_design.md §6.3）。

応答の形（glance/seo/schemas.py）は、本物の GET /api/seo（glance/seo/service.py）と同じ。数字はサイト・日付・期間から決まり、
同じ条件なら同じ数字になる。DB・Google・Bing・利用者のデータには触れない。
"""

import random
from dataclasses import dataclass
from datetime import date
from typing import Any

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
class DemoSite:
    site_id: int
    name: str
    impressions: int  # Google の1日あたりの表示回数の目安
    ctr: float
    position: float
    indexed: int  # Bing のインデックス数の目安
    sitemap: int  # サイトマップの URL 数
    shown: float  # サイトマップのうち、28日間に検索に出るページの割合の目安（Google）


SITES = [
    # Bing のインデックス数は、日がたつほど増える（2026年の終わりに約1.26倍）。サイトマップの URL より少なくなるようにする
    DemoSite(1, "デモサイト A", 11000, 0.026, 11.8, 2600, 3400, 0.82),
    DemoSite(2, "デモサイト B", 3000, 0.024, 17.9, 800, 1100, 0.64),
    DemoSite(3, "デモサイト C", 1500, 0.017, 20.4, 900, 1400, 0.47),
    DemoSite(4, "デモサイト D", 450, 0.018, 24.8, 250, 420, 0.31),
    DemoSite(5, "デモサイト E", 1300, 0.036, 11.5, 2000, 2600, 0.76),
]

BING_SCALE = 0.09  # Bing の表示回数は Google のおよそ1割

_TOPICS = [
    ("2024年問題", "2024-problem"), ("WMS", "wms"), ("自動倉庫", "automated-warehouse"), ("AMR", "amr"),
    ("共同配送", "joint-delivery"), ("ラストワンマイル", "last-one-mile"), ("物流 DX", "logistics-dx"),
    ("3PL", "3pl"), ("クロスドッキング", "cross-docking"), ("モーダルシフト", "modal-shift"), ("SCM", "scm"),
    ("在庫回転率", "inventory-turnover"), ("ピッキング", "picking"), ("ドローン配送", "drone-delivery"),
    ("積載率", "load-factor"), ("EC 物流", "ec-logistics"), ("返品物流", "reverse-logistics"),
    ("フォークリフト", "forklift"), ("物流費", "logistics-cost"), ("RFID", "rfid"), ("需要予測", "demand-forecast"),
    ("TMS", "tms"), ("パレット", "pallet"), ("冷凍倉庫", "cold-storage"),
]
_QUERY_FORMS = ["{t} とは", "{t}", "{t} 比較", "{t} メリット", "{t} 費用", "{t} 事例", "{t} 課題"]
_PAGE_FORMS = [
    ("{t}とは？意味・仕組み・導入のポイントをわかりやすく解説", "/glossary/{s}"),
    ("{t}の事例10選", "/case/{s}"),
    ("{t}の最新動向まとめ", "/news/{s}-trend"),
    ("{t}のツール比較", "/tools/{s}"),
]


def _daily(site: DemoSite, engine: Engine, d: date) -> SeoDay:
    rng = random.Random(f"{site.site_id}:{engine}:{d.isoformat()}")
    weekday = d.weekday()
    if engine == "google":
        week = 0.75 if weekday >= 5 else 1.0
        scale = 1.0
    else:
        week = 0.65 if weekday in (4, 5) else 1.0  # Bing は金・土が低い
        scale = BING_SCALE
    trend = 1 + 0.0012 * (d - date(2026, 1, 1)).days
    impressions = round(site.impressions * scale * week * trend * rng.uniform(0.85, 1.15))
    ctr = site.ctr * (1.1 if engine == "bing" else 1.0) * rng.uniform(0.85, 1.15)
    return SeoDay(
        date=d,
        clicks=round(impressions * ctr),
        impressions=impressions,
        position=round(site.position * rng.uniform(0.93, 1.07), 1) if engine == "google" else None,
    )


def _totals(daily: list[SeoDay], engine: Engine) -> SeoTotals:
    clicks = sum(r.clicks for r in daily)
    impressions = sum(r.impressions for r in daily)
    position = None
    if engine == "google" and impressions:
        # 掲載順位は表示回数の重みつき平均（database_design.md §6）
        position = round(sum((r.position or 0) * r.impressions for r in daily) / impressions, 1)
    return SeoTotals(clicks=clicks, impressions=impressions, position=position)


@dataclass(frozen=True)
class _Item:
    key: str  # クエリか、ページのパス
    title: str | None
    clicks: int
    impressions: int
    position: float


def _items(site: DemoSite, engine: Engine, kind: str, r: Range, total_clicks: int) -> list[_Item]:
    """クエリかページの一覧（クリックの多い順）。数字は期間ごとの揺れを入れて、比べる期間との差が自然に出るようにする。"""
    base_rng = random.Random(f"{site.site_id}:{kind}")
    if kind == "query":
        names = [form.format(t=t) for t, _ in _TOPICS for form in _QUERY_FORMS]
    else:
        names = [f"{title.format(t=t)} | {site.name}\t{path.format(s=s)}" for t, s in _TOPICS for title, path in _PAGE_FORMS]
    base_rng.shuffle(names)
    names = names[:140]
    # クエリの表は、伏せられたクエリなどを含まないので、サイト全体より小さい
    share = 0.55 if kind == "query" else 0.9
    weights = [1 / (i + 1) ** 0.9 for i in range(len(names))]
    scale = total_clicks * share / sum(weights)
    items = []
    for i, name in enumerate(names):
        rng = random.Random(f"{site.site_id}:{engine}:{kind}:{name}:{r.start}:{r.end}")
        clicks = round(weights[i] * scale * rng.uniform(0.6, 1.4))
        ctr = max(0.005, 0.12 / (1 + i * 0.08)) * rng.uniform(0.8, 1.2)
        impressions = max(clicks, round(clicks / ctr)) if clicks else rng.randint(5, 80)
        position = round(min(60.0, 1.5 + i * 0.35 * rng.uniform(0.7, 1.3)), 1) if engine == "google" else round(min(40.0, 2 + i * 0.3), 1)
        if kind == "query":
            items.append(_Item(name, None, clicks, impressions, position))
        else:
            title, path = name.split("\t")
            items.append(_Item(path, title, clicks, impressions, position))
    items.sort(key=lambda x: x.clicks, reverse=True)
    return items


def _ranking(
    site: DemoSite, engine: Engine, kind: str, current: Range, previous: Range | None,
    totals: SeoTotals, compare_totals: SeoTotals | None,
) -> list[SeoQuery | SeoPage]:
    """上位100件と、比べる期間のクリック（比べる期間に無いものは 0。本物と同じ）。"""
    before = None
    if previous is not None and compare_totals is not None:
        before = {item.key: item.clicks for item in _items(site, engine, kind, previous, compare_totals.clicks)}
    result: list[SeoQuery | SeoPage] = []
    for item in _items(site, engine, kind, current, totals.clicks)[:TOP]:
        metrics: dict[str, Any] = {
            "clicks": item.clicks,
            "impressions": item.impressions,
            "position": item.position,
            "compare_clicks": before.get(item.key, 0) if before is not None else None,
        }
        result.append(
            SeoQuery(query=item.key, **metrics) if kind == "query" else SeoPage(title=item.title, path=item.key, **metrics)
        )
    return result


def _crawl(site: DemoSite, r: Range) -> list[CrawlDay]:
    rows = []
    for d in r.dates():
        rng = random.Random(f"{site.site_id}:crawl:{d.isoformat()}")
        growth = 1 + 0.0008 * (d - date(2026, 1, 1)).days
        rows.append(
            CrawlDay(
                date=d,
                crawled=round(site.indexed * 0.15 * rng.uniform(0.5, 1.5)),
                # インデックス数はその日の在庫（足してはいけない）
                indexed=round(site.indexed * growth * rng.uniform(0.98, 1.02)),
                errors=rng.choice([0, 0, 0, 1, 1, 2, 3, 5]),
            )
        )
    return rows


def _index(site: DemoSite, engine: Engine, r: Range, until: date) -> SeoIndex:
    if engine == "bing":
        # Bing のインデックス数は、クロールの数字の期間の最後の日の値（_crawl と同じ数字）
        indexed = _crawl(site, Range(r.end, r.end))[0].indexed
        return SeoIndex(sitemap_urls=site.sitemap, sitemap_checked_at=until, indexed=indexed, pages_shown=None, daily=None)
    # 期間が長いほど、1回でも検索に出るページは多い。日ごとは、その日に出たページ数
    share = min(0.98, site.shown * (r.days / 28) ** 0.25)
    shown = round(site.sitemap * share)
    daily = []
    for d in r.dates():
        rng = random.Random(f"{site.site_id}:index:{d.isoformat()}")
        week = 0.8 if d.weekday() >= 5 else 1.0
        daily.append(IndexDay(date=d, pages=round(site.sitemap * site.shown * 0.45 * week * rng.uniform(0.9, 1.1))))
    return SeoIndex(
        sitemap_urls=site.sitemap,
        sitemap_checked_at=until,
        indexed=shown,
        pages_shown=shown + round(site.sitemap * 0.02),  # サイトマップに無いのに出たページも少しある
        daily=daily,
    )


def demo_seo(
    engine: Engine,
    period: PeriodName,
    compare: CompareName,
    today: date,
    start: date | None = None,
    end: date | None = None,
) -> Seo:
    until = default_data_until(engine, today)
    current = resolve_period(period, until, start, end)
    previous = resolve_compare(compare, period, current)
    sites = []
    for site in SITES:
        daily = [_daily(site, engine, d) for d in current.dates()]
        totals = _totals(daily, engine)
        compare_daily = [_daily(site, engine, d) for d in previous.dates()] if previous else None
        compare_totals = _totals(compare_daily, engine) if compare_daily is not None else None
        sites.append(
            SeoSite(
                site_id=site.site_id,
                name=site.name,
                totals=totals,
                compare_totals=compare_totals,
                daily=daily,
                compare_daily=compare_daily,
                # Bing のクエリは今は取らない（data_sources.md §4）
                queries=_ranking(site, engine, "query", current, previous, totals, compare_totals) if engine == "google" else [],
                pages=_ranking(site, engine, "page", current, previous, totals, compare_totals),
                crawl=_crawl(site, current) if engine == "bing" else None,
                index=_index(site, engine, current, until),
            )
        )
    return Seo(
        engine=engine,
        period=SeoSpan.of(current),
        compare=SeoSpan.of(previous) if previous else None,
        data_until=until,
        sites=sites,
    )

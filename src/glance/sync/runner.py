"""Search Console・Bing の取り込み（data_sources.md §1・§3・§4・§6、database_design.md §4・§5）。

コマンドは python -m glance.sync（glance/sync/__main__.py）。紐づけたサイトだけを取る。

- GSC: 表ごとに「取得済みの最終日の3日前」から今日までを、1日ずつ取り直して上書きする。初めては16ヶ月前から。
  1日分は、消してから入れ直す（取り直しで消えた行も消える）。途中で失敗したら、その表はそこで止める
  （次回は、取得済みの最終日から続ける）。少ないクエリは、月の数字が確定した後（翌月8日以降）に整理する。
- サイトマップ: Search Console に登録したサイトマップを読み、載っている URL（パス）を入れ替える（インデックスの目安に使う）。
- Bing: API は日付を選べず、取れる範囲（日次は約98日、ページ別は13週）を毎回返すので、全部を上書きする。
- 取得ごとに取得ログ（sync_runs）を残す。
"""

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glance.auth.crypto import TokenCipher
from glance.bing.client import BingClient
from glance.db.models import (
    Base,
    BingCrawlDaily,
    BingKey,
    BingPageWeekly,
    BingSiteDaily,
    Connection,
    GscPage,
    GscQueryPage,
    GscSite,
    Site,
    SitemapUrl,
    SyncRun,
    User,
)
from glance.google.factory import GoogleFactory
from glance.google.client import GoogleClient, GoogleQuotaExceeded, GscRow
from glance.sync.sitemap import SitemapFetcher, sitemap_paths
from glance.sync.values import bing_date, country_code, device, page_path

BACKFILL_MONTHS = 16  # GSC は16ヶ月前まで（data_sources.md §6）
OVERLAP_DAYS = 3  # 直近は確定していないので、取得済みの最終日の3日前から取り直す（data_sources.md §1）
ROW_LIMIT = 25_000  # 1回の取得の上限。これを超える日は startRow で続きを取る
# GSC の上限は、利用者ごとに1分1,200回。同時に呼ぶのは3つまでにし、上限に当たったら待ってやり直す
GSC_CONCURRENCY = 3
GSC_RETRIES = 5
GSC_BACKOFF_SECONDS = 15.0  # 15秒、30秒、60秒…と待つ
SMALL_QUERY_IMPRESSIONS = 10  # 月の表示回数がこれ未満のクエリを整理する（data_sources.md §3）
CHUNK = 1_000  # 1回の INSERT に入れる行数

GSC_TABLES: dict[str, tuple[type[Base], list[str]]] = {
    "gsc_site": (GscSite, ["date", "country", "device"]),
    "gsc_page": (GscPage, ["date", "page", "device"]),
    "gsc_query_page": (GscQueryPage, ["date", "query", "page"]),
}


@dataclass
class Outcome:
    site: str
    source: str
    table: str
    start: date | None
    end: date | None
    rows: int
    error: str | None = None


def months_ago(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def _next_month(month: date) -> date:
    return months_ago(month, -1)


def _error(e: BaseException) -> str:
    return f"{type(e).__name__}: {e}"[:500]


# --- GSC: 1行をそろえる ---------------------------------------------------------------------


def _gsc_key(dims: list[str], row: GscRow) -> tuple[Any, ...]:
    convert: dict[str, Callable[[str], Any]] = {
        "date": date.fromisoformat,
        "country": country_code,
        "device": device,
        "page": page_path,
        "query": str,
    }
    return tuple(convert[dim](value) for dim, value in zip(dims, row.keys, strict=True))


def gsc_values(site_id: int, dims: list[str], rows: Iterable[GscRow]) -> list[dict[str, Any]]:
    """API の行を表の行にする。そろえた後に同じ軸になった行（パスが同じ URL など）は足し合わせる。"""
    merged: dict[tuple[Any, ...], list[float]] = {}
    for row in rows:
        total = merged.setdefault(_gsc_key(dims, row), [0, 0, 0.0])
        total[0] += row.clicks
        total[1] += row.impressions
        total[2] += row.position * row.impressions
    values = []
    for key, (clicks, impressions, weighted) in merged.items():
        value = dict(zip(dims, key, strict=True))
        value.update(
            site_id=site_id,
            clicks=int(clicks),
            impressions=int(impressions),
            position=weighted / impressions if impressions else 0.0,
            position_weighted=weighted,
        )
        values.append(value)
    return values


# --- Bing: 1件をそろえる --------------------------------------------------------------------


def _bing_position(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and value > 0 else None


def bing_values(site_id: int, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if table == "bing_site_daily":
        return [
            {"site_id": site_id, "date": bing_date(r["Date"]), "clicks": r["Clicks"], "impressions": r["Impressions"], "raw": r}
            for r in rows
        ]
    if table == "bing_crawl_daily":
        return [
            {
                "site_id": site_id,
                "date": bing_date(r["Date"]),
                "crawled": r.get("CrawledPages", 0),
                "indexed": r.get("InIndex", 0),
                "backlinks": r.get("InLinks", 0),
                "crawl_errors": r.get("CrawlErrors", 0),
                "raw": r,
            }
            for r in rows
        ]
    # ページ別（週次）。URL をパスにそろえ、同じパスになったものは足し合わせる（raw は元の件を並べて残す）
    merged: dict[tuple[date, str], list[dict[str, Any]]] = {}
    for r in rows:
        merged.setdefault((bing_date(r["Date"]), page_path(r["Query"])), []).append(r)
    values = []
    for (week, page), group in merged.items():
        impressions = sum(r["Impressions"] for r in group)
        positioned = [(p, r["Impressions"]) for r in group if (p := _bing_position(r.get("AvgImpressionPosition")))]
        weight = sum(w for _, w in positioned)
        values.append(
            {
                "site_id": site_id,
                "week": week,
                "page": page,
                "clicks": sum(r["Clicks"] for r in group),
                "impressions": impressions,
                "position": sum(p * w for p, w in positioned) / weight if weight else None,
                "raw": group[0] if len(group) == 1 else {"merged": group},
            }
        )
    return values


BING_TABLES: dict[str, tuple[str, type[Base], list[str]]] = {
    "bing_site_daily": ("GetRankAndTrafficStats", BingSiteDaily, ["site_id", "date"]),
    "bing_page_weekly": ("GetPageStats", BingPageWeekly, ["site_id", "week", "page"]),
    "bing_crawl_daily": ("GetCrawlStats", BingCrawlDaily, ["site_id", "date"]),
}


# --- 取り込み ---------------------------------------------------------------------------------


class Syncer:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        google_factory: GoogleFactory,
        bing_client: BingClient,
        cipher: TokenCipher | None,
        today: date,
        *,
        sitemap_fetcher: SitemapFetcher,
        report: Callable[[Outcome], None] = lambda _o: None,
    ) -> None:
        self._sessions = sessionmaker
        self._sitemaps = sitemap_fetcher
        self._google_factory = google_factory
        self._bing = bing_client
        self._cipher = cipher
        self._today = today
        self._report = report
        self._gsc_slots = asyncio.Semaphore(GSC_CONCURRENCY)

    async def run(self, sources: set[str], site_ids: list[int] | None = None) -> list[Outcome]:
        """紐づけた（接続設定の行がある）サイト・ソースを取る。1つが落ちても、ほかは続ける。"""
        async with self._sessions() as db:
            query = (
                select(Site, Connection)
                .join(Connection, Connection.site_id == Site.id)
                .where(Connection.source.in_(sources & {"gsc", "bing"}))
                .order_by(Site.sort_order, Site.id, Connection.source)
            )
            if site_ids:
                query = query.where(Site.id.in_(site_ids))
            pairs = [(site, connection) for site, connection in await db.execute(query)]
        jobs = [self._gsc(site, c) if c.source == "gsc" else self._bing_site(site, c) for site, c in pairs]
        # サイト・ソースごとに並べて取る（GSC の上限は、サイトと利用者ごとに1分1,200回）
        results = await asyncio.gather(*jobs, return_exceptions=True)
        outcomes: list[Outcome] = []
        for (site, c), result in zip(pairs, results, strict=True):
            if isinstance(result, BaseException):
                # 取得ログも書けなかった（DB のエラーなど）。結果にだけ出す
                failed = Outcome(site.name, c.source, "-", None, None, 0, _error(result))
                self._report(failed)
                outcomes.append(failed)
            else:
                outcomes.extend(result)
        return outcomes

    async def _log(self, site: Site, source: str, table: str, target: str | None, start: date | None,
                   end: date | None, rows: int, error: str | None, started_at: datetime) -> Outcome:
        async with self._sessions() as db:
            db.add(
                SyncRun(site_id=site.id, source=source, table_name=table, target=target, start_date=start, end_date=end,
                        rows=rows, ok=error is None, error=error, started_at=started_at)
            )
            await db.commit()
        outcome = Outcome(site.name, source, table, start, end, rows, error)
        self._report(outcome)
        return outcome

    # --- GSC -----------------------------------------------------------------------------

    async def _gsc(self, site: Site, connection: Connection) -> list[Outcome]:
        started_at = datetime.now(UTC)
        target = connection.target
        assert target
        try:
            async with self._sessions() as db:
                user = await db.get(User, connection.user_id) if connection.user_id else None
            if user is None:
                raise RuntimeError("紐づけた利用者がいません。サイト設定で Search Console を紐づけ直してください")
            client = self._google_factory(user)
        except Exception as e:  # noqa: BLE001 ログに残して、ほかのサイトは続ける
            return [await self._log(site, "gsc", table, target, None, None, 0, _error(e), started_at) for table in GSC_TABLES]
        outcomes = list(await asyncio.gather(*(self._gsc_table(site, target, client, table) for table in GSC_TABLES)))
        query_run = next(o for o in outcomes if o.table == "gsc_query_page")
        # 途中で失敗した月は、月の数字がそろっていないので整理しない（次回、取り終えてから整理する）
        if query_run.error is None and query_run.start is not None and query_run.end is not None:
            outcomes.append(await self._clean_queries(site, target, query_run.start, query_run.end))
        outcomes.append(await self._sitemap(site, target, client))
        return outcomes

    async def _sitemap(self, site: Site, target: str, client: GoogleClient) -> Outcome:
        """サイトマップの URL を入れ替える。読めなかったら前のままにする。紐づけたサイトの外は読まない。"""
        started_at = datetime.now(UTC)
        try:
            async with self._gsc_slots:
                sitemaps = await client.gsc_sitemaps(target)
            if not sitemaps:
                raise RuntimeError("Search Console にサイトマップが登録されていません")
            paths = sorted(await sitemap_paths(self._sitemaps, sitemaps, target))
            async with self._sessions() as db:
                await db.execute(delete(SitemapUrl).where(SitemapUrl.site_id == site.id))
                for i in range(0, len(paths), CHUNK):
                    await db.execute(pg_insert(SitemapUrl), [{"site_id": site.id, "path": p} for p in paths[i : i + CHUNK]])
                await db.commit()
        except Exception as e:  # noqa: BLE001
            return await self._log(site, "gsc", "sitemap_urls", target, None, None, 0, _error(e), started_at)
        return await self._log(site, "gsc", "sitemap_urls", target, self._today, self._today, len(paths), None, started_at)

    async def _gsc_start(self, site_id: int, model: type[Base], table: str) -> date:
        """取得済みの最終日の3日前。数字のある最終日を使う（直近の確定していない日を取り直すため）。

        まだ数字が1日もなければ（サイトを始める前の期間など）、前回までに取り終えた日から続ける。
        """
        backfill = months_ago(self._today, BACKFILL_MONTHS)
        async with self._sessions() as db:
            latest = await db.scalar(select(func.max(model.date)).where(model.site_id == site_id))  # type: ignore[attr-defined]
            if latest is None:
                latest = await db.scalar(
                    select(func.max(SyncRun.end_date)).where(SyncRun.site_id == site_id, SyncRun.table_name == table)
                )
        return backfill if latest is None else max(backfill, latest - timedelta(days=OVERLAP_DAYS))

    async def _gsc_call(self, client: GoogleClient, site_url: str, day: date, dims: list[str], start_row: int) -> list[GscRow]:
        for attempt in range(GSC_RETRIES + 1):
            async with self._gsc_slots:
                try:
                    return await client.gsc_search_analytics(site_url, day, day, dims, start_row, ROW_LIMIT)
                except GoogleQuotaExceeded:
                    if attempt == GSC_RETRIES:
                        raise
            await asyncio.sleep(GSC_BACKOFF_SECONDS * 2**attempt)
        raise AssertionError("unreachable")

    async def _gsc_table(self, site: Site, target: str, client: GoogleClient, table: str) -> Outcome:
        model, dims = GSC_TABLES[table]
        started_at = datetime.now(UTC)
        start = await self._gsc_start(site.id, model, table)
        day, rows, error = start, 0, None
        try:
            while day <= self._today:
                rows += await self._gsc_day(site.id, target, client, model, dims, day)
                day += timedelta(days=1)
        except Exception as e:  # noqa: BLE001 ここで止め、次回は取得済みの最終日から続ける
            error = _error(e)
        end = day - timedelta(days=1) if day > start else None
        return await self._log(site, "gsc", table, target, start, end, rows, error, started_at)

    async def _gsc_day(self, site_id: int, site_url: str, client: GoogleClient, model: type[Base], dims: list[str],
                       day: date) -> int:
        fetched: list[GscRow] = []
        while True:
            page = await self._gsc_call(client, site_url, day, dims, len(fetched))
            fetched.extend(page)
            if len(page) < ROW_LIMIT:
                break
        values = gsc_values(site_id, dims, fetched)
        async with self._sessions() as db:
            await db.execute(delete(model).where(model.site_id == site_id, model.date == day))  # type: ignore[attr-defined]
            for i in range(0, len(values), CHUNK):
                await db.execute(pg_insert(model), values[i : i + CHUNK])
            await db.commit()
        return len(values)

    async def _clean_queries(self, site: Site, target: str, start: date, end: date) -> Outcome:
        """月の数字が確定した後（翌月8日以降）に、その月の表示回数が10回未満のクエリを、クエリ表から消す。

        今回取った月と、まだ整理していない月が対象。取れる最初の月（16ヶ月前）は、Search Console に月の途中から
        しか残っておらず月の数字がそろわないので整理しない。サイト全体の数字は gsc_site から出すので影響しない。
        """
        started_at = datetime.now(UTC)
        oldest = months_ago(self._today, BACKFILL_MONTHS)
        async with self._sessions() as db:
            done = set(
                await db.scalars(
                    select(SyncRun.start_date).where(
                        SyncRun.site_id == site.id, SyncRun.table_name == "gsc_query_cleanup", SyncRun.ok
                    )
                )
            )
            months_with_data = {
                m.date() if isinstance(m, datetime) else m
                for m in await db.scalars(
                    select(func.date_trunc("month", GscQueryPage.date)).where(GscQueryPage.site_id == site.id).distinct()
                )
            }
            fetched = set()
            month = start.replace(day=1)
            while month <= end:
                fetched.add(month)
                month = _next_month(month)
            eligible = {
                m
                for m in fetched | (months_with_data - done)
                if m > oldest and self._today >= _next_month(m) + timedelta(days=7)
            }
            removed = 0
            for month in sorted(eligible):
                result = await db.execute(
                    text(
                        """
                        DELETE FROM gsc_query_page q
                        USING (
                            SELECT query FROM gsc_query_page
                            WHERE site_id = :site AND date >= :start AND date < :end
                            GROUP BY query HAVING sum(impressions) < :minimum
                        ) small
                        WHERE q.site_id = :site AND q.date >= :start AND q.date < :end AND q.query = small.query
                        """
                    ),
                    {"site": site.id, "start": month, "end": _next_month(month), "minimum": SMALL_QUERY_IMPRESSIONS},
                )
                removed += result.rowcount  # type: ignore[attr-defined]
                db.add(
                    SyncRun(site_id=site.id, source="gsc", table_name="gsc_query_cleanup", target=target,
                            start_date=month, end_date=_next_month(month) - timedelta(days=1),
                            rows=result.rowcount, ok=True, started_at=started_at)  # type: ignore[attr-defined]
                )
            await db.commit()
        outcome = Outcome(site.name, "gsc", "gsc_query_cleanup", min(eligible, default=None),
                          max(eligible, default=None), removed)
        self._report(outcome)
        return outcome

    # --- Bing ----------------------------------------------------------------------------

    async def _bing_site(self, site: Site, connection: Connection) -> list[Outcome]:
        started_at = datetime.now(UTC)
        target = connection.target
        assert target
        try:
            if self._cipher is None:
                raise RuntimeError("暗号化の鍵（GLANCE_TOKEN_KEY）が設定されていません")
            async with self._sessions() as db:
                key = await db.get(BingKey, connection.bing_key_id) if connection.bing_key_id else None
            if key is None:
                raise RuntimeError("Bing のキーがありません。サイト設定で Bing を紐づけ直してください")
            api_key = self._cipher.decrypt(key.key_encrypted)
        except Exception as e:  # noqa: BLE001
            return [await self._log(site, "bing", table, target, None, None, 0, _error(e), started_at) for table in BING_TABLES]
        return [await self._bing_table(site, target, api_key, table) for table in BING_TABLES]

    async def _bing_table(self, site: Site, target: str, api_key: str, table: str) -> Outcome:
        method, model, keys = BING_TABLES[table]
        started_at = datetime.now(UTC)
        try:
            values = bing_values(site.id, table, await self._bing.stats(api_key, method, target))
            async with self._sessions() as db:
                for i in range(0, len(values), CHUNK):
                    statement = pg_insert(model).values(values[i : i + CHUNK])
                    columns = {c: statement.excluded[c] for c in values[0] if c not in keys}
                    await db.execute(statement.on_conflict_do_update(index_elements=keys, set_=columns))
                await db.commit()
        except Exception as e:  # noqa: BLE001
            return await self._log(site, "bing", table, target, None, None, 0, _error(e), started_at)
        days = [v.get("date") or v.get("week") for v in values]
        return await self._log(site, "bing", table, target, min(days, default=None), max(days, default=None),
                               len(values), None, started_at)

"""Search Console の取り込み（data_sources.md §1・§3・§6、database_design.md §4）。

- 表ごとに「取得済みの最終日の3日前」から今日までを、1日ずつ取り直して上書きする。初めては16ヶ月前から。
  1日分は、消してから入れ直す（取り直しで消えた行も消える）。途中で失敗したら、その表はそこで止める
  （次回は、取得済みの最終日から続ける）。少ないクエリは、月の数字が確定した後（翌月8日以降）に整理する。
- サイトマップ: Search Console に登録したサイトマップを読み、載っている URL（パス）を入れ替える（インデックスの目安に使う）。
"""

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glance.db.models import Connection, GscPage, GscQueryPage, GscSite, Site, SitemapUrl, SyncRun, User
from glance.google.client import GoogleClient, GoogleQuotaExceeded, GscRow
from glance.google.factory import GoogleFactory
from glance.sync.common import CHUNK, Outcome, SyncLog, error_text
from glance.sync.sitemap import SitemapFetcher, sitemap_paths
from glance.sync.values import country_code, device, page_path

BACKFILL_MONTHS = 16  # GSC は16ヶ月前まで（data_sources.md §6）
OVERLAP_DAYS = 3  # 直近は確定していないので、取得済みの最終日の3日前から取り直す（data_sources.md §1）
ROW_LIMIT = 25_000  # 1回の取得の上限。これを超える日は startRow で続きを取る
# GSC の上限は、利用者ごとに1分1,200回。同時に呼ぶのは3つまでにし、上限に当たったら待ってやり直す
GSC_CONCURRENCY = 3
GSC_RETRIES = 5
GSC_BACKOFF_SECONDS = 15.0  # 15秒、30秒、60秒…と待つ
SMALL_QUERY_IMPRESSIONS = 10  # 月の表示回数がこれ未満のクエリを整理する（data_sources.md §3）

GscModel = type[GscSite] | type[GscPage] | type[GscQueryPage]

# 表と、Search Console に頼む軸（dimensions）
GSC_TABLES: dict[str, tuple[GscModel, list[str]]] = {
    "gsc_site": (GscSite, ["date", "country", "device"]),
    "gsc_page": (GscPage, ["date", "page", "device"]),
    "gsc_query_page": (GscQueryPage, ["date", "query", "page"]),
}
SITEMAP_TABLE = "sitemap_urls"
CLEANUP_TABLE = "gsc_query_cleanup"


def months_ago(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def _next_month(month: date) -> date:
    return months_ago(month, -1)


# --- 1行をそろえる ---------------------------------------------------------------------------


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


# --- 取り込み ---------------------------------------------------------------------------------


class GscSync:
    """1つのサイトの Search Console を取る。紐づけた利用者の許可で呼ぶ。"""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        log: SyncLog,
        today: date,
        google_factory: GoogleFactory,
        sitemap_fetcher: SitemapFetcher,
        allowed_emails: list[str],
    ) -> None:
        self._sessions = sessions
        self._log = log
        self._today = today
        self._google_factory = google_factory
        self._sitemaps = sitemap_fetcher
        self._allowed_emails = {e.lower() for e in allowed_emails}
        self._slots = asyncio.Semaphore(GSC_CONCURRENCY)  # サイトをまたいで、同時に呼ぶ数を抑える

    async def run(self, site: Site, connection: Connection) -> list[Outcome]:
        started_at = datetime.now(UTC)
        target = connection.target
        assert target
        try:
            client = await self._client(site, connection)
        except Exception as e:  # noqa: BLE001 ログに残して、ほかのサイトは続ける
            return [
                await self._log.write(site, "gsc", table, target=target, started_at=started_at, error=error_text(e))
                for table in [*GSC_TABLES, SITEMAP_TABLE]
            ]
        outcomes = list(await asyncio.gather(*(self._table(site, target, client, table) for table in GSC_TABLES)))
        query_run = next(o for o in outcomes if o.table == "gsc_query_page")
        # 途中で失敗した月は、月の数字がそろっていないので整理しない（次回、取り終えてから整理する）
        if query_run.error is None and query_run.start is not None and query_run.end is not None:
            outcomes.append(await self._clean_queries(site, target, query_run.start, query_run.end))
        outcomes.append(await self._sitemap(site, target, client))
        return outcomes

    async def _client(self, site: Site, connection: Connection) -> GoogleClient:
        async with self._sessions() as db:
            user = await db.get(User, connection.user_id) if connection.user_id else None
        if user is None:
            raise RuntimeError("紐づけた利用者がいません。サイト設定で Search Console を紐づけ直してください")
        # 許可リストから外した人・ほかの顧客の人の許可では取らない（API は必ず同じ顧客の人を書くが、念のため）
        if user.email.lower() not in self._allowed_emails:
            raise RuntimeError("紐づけた利用者が許可リストにいません。サイト設定で Search Console を紐づけ直してください")
        if user.tenant_id != site.tenant_id:
            raise RuntimeError("紐づけた利用者が、このサイトの顧客の人ではありません")
        return self._google_factory(user)

    async def _start(self, site_id: int, model: GscModel, table: str) -> date:
        """取得済みの最終日の3日前。数字のある最終日を使う（直近の確定していない日を取り直すため）。

        まだ数字が1日もなければ（サイトを始める前の期間など）、前回までに取り終えた日から続ける。
        """
        backfill = months_ago(self._today, BACKFILL_MONTHS)
        async with self._sessions() as db:
            latest = await db.scalar(select(func.max(model.date)).where(model.site_id == site_id))
            if latest is None:
                latest = await db.scalar(
                    select(func.max(SyncRun.end_date)).where(SyncRun.site_id == site_id, SyncRun.table_name == table)
                )
        return backfill if latest is None else max(backfill, latest - timedelta(days=OVERLAP_DAYS))

    async def _table(self, site: Site, target: str, client: GoogleClient, table: str) -> Outcome:
        model, dims = GSC_TABLES[table]
        started_at = datetime.now(UTC)
        start = await self._start(site.id, model, table)
        day, rows, error = start, 0, None
        try:
            while day <= self._today:
                rows += await self._day(site.id, target, client, model, dims, day)
                day += timedelta(days=1)
        except Exception as e:  # noqa: BLE001 ここで止め、次回は取得済みの最終日から続ける
            error = error_text(e)
        end = day - timedelta(days=1) if day > start else None
        return await self._log.write(
            site, "gsc", table, target=target, started_at=started_at, start=start, end=end, rows=rows, error=error
        )

    async def _day(self, site_id: int, target: str, client: GoogleClient, model: GscModel, dims: list[str], day: date) -> int:
        fetched: list[GscRow] = []
        while True:
            page = await self._call(client, target, day, dims, len(fetched))
            fetched.extend(page)
            if len(page) < ROW_LIMIT:
                break
        values = gsc_values(site_id, dims, fetched)
        async with self._sessions() as db:
            await db.execute(delete(model).where(model.site_id == site_id, model.date == day))
            for i in range(0, len(values), CHUNK):
                await db.execute(pg_insert(model), values[i : i + CHUNK])
            await db.commit()
        return len(values)

    async def _call(self, client: GoogleClient, target: str, day: date, dims: list[str], start_row: int) -> list[GscRow]:
        for attempt in range(GSC_RETRIES + 1):
            async with self._slots:
                try:
                    return await client.gsc_search_analytics(target, day, day, dims, start_row, ROW_LIMIT)
                except GoogleQuotaExceeded:
                    if attempt == GSC_RETRIES:
                        raise
            await asyncio.sleep(GSC_BACKOFF_SECONDS * 2**attempt)
        raise AssertionError("unreachable")

    async def _clean_queries(self, site: Site, target: str, start: date, end: date) -> Outcome:
        """月の数字が確定した後（翌月8日以降）に、その月の表示回数が10回未満のクエリを、クエリ表から消す。

        今回取った月と、まだ整理していない月が対象。取れる最初の月（16ヶ月前）は、Search Console に月の途中から
        しか残っておらず月の数字がそろわないので整理しない。サイト全体の数字は gsc_site から出すので影響しない。
        月ごとに、取得ログに整理した月と消した行数を残す。
        """
        started_at = datetime.now(UTC)
        oldest = months_ago(self._today, BACKFILL_MONTHS)
        async with self._sessions() as db:
            done = set(
                await db.scalars(
                    select(SyncRun.start_date).where(SyncRun.site_id == site.id, SyncRun.table_name == CLEANUP_TABLE, SyncRun.ok)
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
                in_month = (
                    (GscQueryPage.site_id == site.id) & (GscQueryPage.date >= month) & (GscQueryPage.date < _next_month(month))
                )
                small = (
                    select(GscQueryPage.query)
                    .where(in_month)
                    .group_by(GscQueryPage.query)
                    .having(func.sum(GscQueryPage.impressions) < SMALL_QUERY_IMPRESSIONS)
                )
                result = await db.execute(
                    delete(GscQueryPage)
                    .where(in_month, GscQueryPage.query.in_(small))
                    .execution_options(synchronize_session=False)
                )
                count: int = result.rowcount  # type: ignore[attr-defined]
                removed += count
                db.add(
                    SyncRun(site_id=site.id, source="gsc", table_name=CLEANUP_TABLE, target=target, start_date=month,
                            end_date=_next_month(month) - timedelta(days=1), rows=count, ok=True, started_at=started_at)
                )
            await db.commit()
        outcome = Outcome(site.name, "gsc", CLEANUP_TABLE, min(eligible, default=None), max(eligible, default=None), removed)
        self._log.report(outcome)
        return outcome

    async def _sitemap(self, site: Site, target: str, client: GoogleClient) -> Outcome:
        """サイトマップの URL を入れ替える。読めなかったら前のままにする。紐づけたサイトの外は読まない。"""
        started_at = datetime.now(UTC)
        try:
            async with self._slots:
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
            return await self._log.write(site, "gsc", SITEMAP_TABLE, target=target, started_at=started_at, error=error_text(e))
        return await self._log.write(
            site, "gsc", SITEMAP_TABLE, target=target, started_at=started_at, start=self._today, end=self._today, rows=len(paths)
        )

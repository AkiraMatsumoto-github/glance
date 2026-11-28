"""Search Console・Bing の取り込み（data_sources.md §1・§3・§4・§6、database_design.md §4・§5）。

コマンドは python -m glance.sync（glance/sync/__main__.py）。紐づけたサイトだけを取る。
取り方は、Search Console が glance/sync/gsc.py、Bing が glance/sync/bing.py。
取得ごとに取得ログ（sync_runs）を残す（glance/sync/common.py）。
"""

import asyncio
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glance.auth.crypto import TokenCipher
from glance.bing.client import BingClient
from glance.db.models import Connection, Site
from glance.google.factory import GoogleFactory
from glance.sync.bing import BingSync
from glance.sync.common import Outcome, SyncLog, error_text
from glance.sync.gsc import GscSync
from glance.sync.sitemap import SitemapFetcher


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
        allowed_emails: list[str],
        report: Callable[[Outcome], None] = lambda _o: None,
    ) -> None:
        self._sessions = sessionmaker
        self._report = report
        log = SyncLog(sessionmaker, report)
        self._sources = {
            "gsc": GscSync(sessionmaker, log, today, google_factory, sitemap_fetcher, allowed_emails),
            "bing": BingSync(sessionmaker, log, bing_client, cipher),
        }

    async def run(self, sources: set[str], site_ids: list[int] | None = None) -> list[Outcome]:
        """紐づけた（接続設定の行がある）サイト・ソースを取る。1つが落ちても、ほかは続ける。"""
        async with self._sessions() as db:
            query = (
                select(Site, Connection)
                .join(Connection, Connection.site_id == Site.id)
                .where(Connection.source.in_(sources & set(self._sources)))
                .order_by(Site.sort_order, Site.id, Connection.source)
            )
            if site_ids:
                query = query.where(Site.id.in_(site_ids))
            pairs = [(site, connection) for site, connection in await db.execute(query)]
        # サイト・ソースごとに並べて取る（GSC の上限は、サイトと利用者ごとに1分1,200回）
        jobs = [self._sources[c.source].run(site, c) for site, c in pairs]
        results = await asyncio.gather(*jobs, return_exceptions=True)
        outcomes: list[Outcome] = []
        for (site, c), result in zip(pairs, results, strict=True):
            if isinstance(result, BaseException):
                # 取得ログも書けなかった（DB のエラーなど）。結果にだけ出す
                failed = Outcome(site.name, c.source, "-", None, None, 0, error_text(result))
                self._report(failed)
                outcomes.append(failed)
            else:
                outcomes.extend(result)
        return outcomes

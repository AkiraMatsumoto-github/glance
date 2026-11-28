"""Bing の取り込み（data_sources.md §4・§6、database_design.md §5）。

API は日付を選べず、取れる範囲（日次は約98日、ページ別は13週）を毎回返すので、全部を上書きする。
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glance.auth.crypto import TokenCipher
from glance.bing.client import BingClient
from glance.db.models import BingCrawlDaily, BingKey, BingPageWeekly, BingSiteDaily, Connection, Site
from glance.sync.common import CHUNK, Outcome, SyncLog, error_text
from glance.sync.values import bing_date, page_path

BingModel = type[BingSiteDaily] | type[BingPageWeekly] | type[BingCrawlDaily]

# 表と、呼ぶ API・上書きの鍵にする列
BING_TABLES: dict[str, tuple[str, BingModel, list[str]]] = {
    "bing_site_daily": ("GetRankAndTrafficStats", BingSiteDaily, ["site_id", "date"]),
    "bing_page_weekly": ("GetPageStats", BingPageWeekly, ["site_id", "week", "page"]),
    "bing_crawl_daily": ("GetCrawlStats", BingCrawlDaily, ["site_id", "date"]),
}


# --- 1件をそろえる ---------------------------------------------------------------------------


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


# --- 取り込み ---------------------------------------------------------------------------------


class BingSync:
    """1つのサイトの Bing を取る。紐づけたキーで呼ぶ。"""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], log: SyncLog, client: BingClient, cipher: TokenCipher | None
    ) -> None:
        self._sessions = sessions
        self._log = log
        self._client = client
        self._cipher = cipher

    async def run(self, site: Site, connection: Connection) -> list[Outcome]:
        started_at = datetime.now(UTC)
        target = connection.target
        assert target
        try:
            api_key = await self._api_key(site, connection)
        except Exception as e:  # noqa: BLE001 ログに残して、ほかのサイトは続ける
            return [
                await self._log.write(site, "bing", table, target=target, started_at=started_at, error=error_text(e))
                for table in BING_TABLES
            ]
        return [await self._table(site, target, api_key, table) for table in BING_TABLES]

    async def _api_key(self, site: Site, connection: Connection) -> str:
        if self._cipher is None:
            raise RuntimeError("暗号化の鍵（GLANCE_TOKEN_KEY）が設定されていません")
        async with self._sessions() as db:
            key = await db.get(BingKey, connection.bing_key_id) if connection.bing_key_id else None
        if key is None:
            raise RuntimeError("Bing のキーがありません。サイト設定で Bing を紐づけ直してください")
        if key.tenant_id != site.tenant_id:  # API は必ず同じ顧客のキーを書くが、念のため
            raise RuntimeError("紐づけた Bing のキーが、このサイトの顧客のものではありません")
        return self._cipher.decrypt(key.key_encrypted)

    async def _table(self, site: Site, target: str, api_key: str, table: str) -> Outcome:
        method, model, keys = BING_TABLES[table]
        started_at = datetime.now(UTC)
        try:
            values = bing_values(site.id, table, await self._client.stats(api_key, method, target))
            async with self._sessions() as db:
                for i in range(0, len(values), CHUNK):
                    statement = pg_insert(model).values(values[i : i + CHUNK])
                    columns = {c: statement.excluded[c] for c in values[0] if c not in keys}
                    await db.execute(statement.on_conflict_do_update(index_elements=keys, set_=columns))
                await db.commit()
        except Exception as e:  # noqa: BLE001
            return await self._log.write(site, "bing", table, target=target, started_at=started_at, error=error_text(e))
        days = [v.get("date") or v.get("week") for v in values]
        return await self._log.write(
            site, "bing", table, target=target, started_at=started_at,
            start=min(days, default=None), end=max(days, default=None), rows=len(values),
        )

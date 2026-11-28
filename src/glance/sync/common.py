"""取り込みの共通の部品。取得ログ（sync_runs）を書き、結果を報告する。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glance.db.models import Site, SyncRun

CHUNK = 1_000  # 1回の INSERT に入れる行数


@dataclass
class Outcome:
    site: str
    source: str
    table: str
    start: date | None
    end: date | None
    rows: int
    error: str | None = None


def error_text(e: BaseException) -> str:
    return f"{type(e).__name__}: {e}"[:500]


class SyncLog:
    """取得ログを1行書き、その結果を報告する（コマンドは1行ずつ表示する）。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], report: Callable[[Outcome], None]) -> None:
        self._sessions = sessions
        self.report = report

    async def write(
        self,
        site: Site,
        source: str,
        table: str,
        *,
        target: str,
        started_at: datetime,
        start: date | None = None,
        end: date | None = None,
        rows: int = 0,
        error: str | None = None,
    ) -> Outcome:
        async with self._sessions() as db:
            db.add(
                SyncRun(site_id=site.id, source=source, table_name=table, target=target, start_date=start, end_date=end,
                        rows=rows, ok=error is None, error=error, started_at=started_at)
            )
            await db.commit()
        outcome = Outcome(site.name, source, table, start, end, rows, error)
        self.report(outcome)
        return outcome

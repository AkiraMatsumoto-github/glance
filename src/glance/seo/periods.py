"""SEO の画面の期間と比べる期間（screen_design.md §7、api_design.md §1 の period・compare と同じ解釈）。

期間の終わりは、そのソースのデータがある最終日（data_until）まで。デモと本物で共通に使う。
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

PeriodName = Literal["last_7_days", "last_28_days", "this_month", "last_month", "custom"]
CompareName = Literal["previous_period", "previous_year", "none"]

PERIOD_LABELS: dict[str, str] = {
    "last_7_days": "直近7日",
    "last_28_days": "直近28日",
    "this_month": "今月",
    "last_month": "先月",
    "custom": "指定",
}


class PeriodError(ValueError):
    """期間の指定がおかしい（画面にそのまま出す文を持つ）。"""


@dataclass(frozen=True)
class Range:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _previous_month(d: date) -> Range:
    end = _month_start(d) - timedelta(days=1)
    return Range(_month_start(end), end)


def _minus_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 2/29
        return d.replace(year=d.year - 1, day=28)


def resolve_period(
    period: PeriodName, data_until: date, start: date | None = None, end: date | None = None
) -> Range:
    if period == "last_7_days":
        return Range(data_until - timedelta(days=6), data_until)
    if period == "last_28_days":
        return Range(data_until - timedelta(days=27), data_until)
    if period == "this_month":
        return Range(_month_start(data_until), data_until)
    if period == "last_month":
        return _previous_month(data_until)
    if start is None or end is None:
        raise PeriodError("期間の始まりと終わりを指定してください")
    if start > end:
        raise PeriodError("期間の始まりが終わりより後になっています")
    if start > data_until:
        raise PeriodError(f"{data_until.isoformat()} より後のデータはまだありません")
    # 終わりはデータがある最終日まで
    return Range(start, min(end, data_until))


def resolve_compare(compare: CompareName, period: PeriodName, current: Range) -> Range | None:
    if compare == "none":
        return None
    if compare == "previous_year":
        return Range(_minus_year(current.start), _minus_year(current.end))
    # 前の期間。今月・先月は前の月の全体、それ以外は直前の同じ日数
    if period in ("this_month", "last_month"):
        return _previous_month(current.start)
    end = current.start - timedelta(days=1)
    return Range(end - timedelta(days=current.days - 1), end)

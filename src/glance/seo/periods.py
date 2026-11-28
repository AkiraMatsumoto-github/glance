"""SEO の画面の検索エンジン・期間・比べる期間（screen_design.md §7、api_design.md §1 の period・compare と同じ解釈）。

期間の終わりは、そのソースのデータがある最終日（data_until）まで。デモと本物で共通に使う。
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

Engine = Literal["google", "bing"]
PeriodName = Literal["last_7_days", "last_28_days", "this_month", "last_month", "custom"]
CompareName = Literal["previous_period", "previous_year", "none"]


class PeriodError(ValueError):
    """期間の指定がおかしい（画面にそのまま出す文を持つ）。"""


# 指定の期間の上限。長い期間は、日を全部並べる集計が重くなり、ほかの要求を止めてしまう（ログイン不要のデモもある）。
# GSC の保存期間（16ヶ月）が収まる長さにする
MAX_CUSTOM_DAYS = 500
# 指定の期間の始まりは、データがある最終日の3年前まで（それより前のデータは、どのソースにも無い）
EARLIEST_YEARS = 3


@dataclass(frozen=True)
class Range:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def dates(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range(self.days)]


def default_data_until(engine: Engine, today: date) -> date:
    """データがある最終日の既定。GSC は確定まで2〜3日、Bing は前日まで。

    デモはいつもこれを使う。本物は取り込んだ数字の最終日を使い、まだ何も無いときだけこれを使う。
    """
    return today - timedelta(days=3 if engine == "google" else 1)


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
    earliest = data_until
    for _ in range(EARLIEST_YEARS):
        earliest = _minus_year(earliest)
    if start < earliest:
        raise PeriodError(f"{earliest.isoformat()} より前は指定できません")
    # 終わりはデータがある最終日まで
    current = Range(start, min(end, data_until))
    if current.days > MAX_CUSTOM_DAYS:
        raise PeriodError(f"期間は {MAX_CUSTOM_DAYS} 日までにしてください")
    return current


def resolve_compare(compare: CompareName, period: PeriodName, current: Range) -> Range | None:
    try:
        return _compare(compare, period, current)
    except (OverflowError, ValueError) as e:  # 日付の範囲の外（期間の下限があるので、ふつうは起きない）
        raise PeriodError("比べる期間を決められません") from e


def _compare(compare: CompareName, period: PeriodName, current: Range) -> Range | None:
    if compare == "none":
        return None
    if compare == "previous_year":
        return Range(_minus_year(current.start), _minus_year(current.end))
    # 前の期間。今月・先月は前の月の全体、それ以外は直前の同じ日数
    if period in ("this_month", "last_month"):
        return _previous_month(current.start)
    end = current.start - timedelta(days=1)
    return Range(end - timedelta(days=current.days - 1), end)

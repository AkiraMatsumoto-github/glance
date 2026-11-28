"""取り込むときの値のそろえ方（database_design.md §7）。"""

import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import unquote, urlsplit

import pycountry

NOT_SET = "(not set)"


def page_path(url: str) -> str:
    """完全な URL をパスにする。ホスト名・クエリ文字列・# 以降を除き、パーセントエンコードを解除する。"""
    return unquote(urlsplit(url).path) or "/"


def country_code(alpha3: str) -> str:
    """GSC の3文字の国コード（jpn）を2文字（JP）にする。分からない国（zzz など）は (not set)。"""
    found = pycountry.countries.get(alpha_3=alpha3.upper())
    return found.alpha_2 if found else NOT_SET


def device(value: str) -> str:
    return value.lower()


_BING_DATE = re.compile(r"/Date\((-?\d+)([+-]\d{4})?\)/")


def bing_date(value: str) -> date:
    """Bing の /Date(1700035200000-0800)/ を日付にする。ずれがあれば、その地域の日付にする（なければ UTC）。"""
    found = _BING_DATE.fullmatch(value)
    if not found:
        raise ValueError(f"Bing の日付の形ではありません: {value}")
    moment = datetime.fromtimestamp(int(found.group(1)) / 1000, UTC)
    if found.group(2):
        sign = 1 if found.group(2)[0] == "+" else -1
        moment += sign * timedelta(hours=int(found.group(2)[1:3]), minutes=int(found.group(2)[3:5]))
    return moment.date()

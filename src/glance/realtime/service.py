"""全サイトのリアルタイムを取ってまとめる（data_sources.md §5、technical_design.md §6.1）。

結果は DB に入れない。キャッシュもしない。
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from glance.google.ga4 import BreakdownRow, EventRow, Ga4Client, Ga4PermissionDenied, Ga4QuotaExceeded, ReauthRequired, Totals

log = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")
MINUTES = 30
TOP_PAGES = 20
TOP_EVENTS = 20  # 画面では、選んだサイトを合わせて回数の多い10件を出す
TOP_COUNTRIES = 10  # 画面では、選んだサイトで UU の多い国を3つ出し、残りは「その他」にまとめる
SITE_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class SiteTarget:
    site_id: int
    name: str
    property_id: str


def _totals(t: Totals) -> dict[str, int]:
    return {"page_views": t.page_views, "active_users": t.active_users, "key_events": t.key_events}


def _events(rows: list[EventRow]) -> list[dict[str, Any]]:
    return [{"name": r.name, "event_count": r.event_count} for r in rows]


def _breakdown(rows: list[BreakdownRow]) -> list[dict[str, Any]]:
    return [{"key": r.key, "active_users": r.active_users} for r in rows]


async def _fetch_site(client: Ga4Client, target: SiteTarget, timeout: float) -> dict[str, Any]:
    base = {"site_id": target.site_id, "name": target.name}
    try:
        async with asyncio.timeout(timeout):
            last_30, minutes, pages, devices, countries, events = await asyncio.gather(
                client.realtime_totals(target.property_id),
                client.realtime_per_minute(target.property_id),
                client.realtime_top_pages(target.property_id, TOP_PAGES),
                # デバイスは mobile・desktop・tablet ほどしかないので、上限は余裕をもって取る
                client.realtime_breakdown(target.property_id, "deviceCategory", 10),
                client.realtime_breakdown(target.property_id, "countryId", TOP_COUNTRIES),
                client.realtime_events(target.property_id, TOP_EVENTS),
            )
    except ReauthRequired:
        raise
    except TimeoutError:
        return {**base, "status": "error", "error": "timeout"}
    except Ga4PermissionDenied:
        return {**base, "status": "error", "error": "permission_denied"}
    except Ga4QuotaExceeded:
        return {**base, "status": "error", "error": "quota"}
    except Exception:
        log.exception("リアルタイムを取れなかった: site_id=%s", target.site_id)
        return {**base, "status": "error", "error": "error"}

    # 値のない分を 0 で埋め、30分前から今までの30個にそろえる
    by_minute = {m.minutes_ago: m for m in minutes}
    per_minute = []
    for minutes_ago in range(MINUTES - 1, -1, -1):
        m = by_minute.get(minutes_ago)
        per_minute.append(
            {
                "minutes_ago": minutes_ago,
                "page_views": m.page_views if m else 0,
                "active_users": m.active_users if m else 0,
            }
        )
    return {
        **base,
        "status": "ok",
        "last_30_min": _totals(last_30),
        "per_minute": per_minute,
        "top_pages": [
            {"title": p.title, "page_views": p.page_views, "active_users": p.active_users} for p in pages[:TOP_PAGES]
        ],
        "devices": _breakdown(devices),
        "countries": _breakdown(countries[:TOP_COUNTRIES]),
        "events": _events(events[:TOP_EVENTS]),
    }


async def fetch_realtime(
    client: Ga4Client,
    targets: list[SiteTarget],
    timeout: float = SITE_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    sites = list(await asyncio.gather(*(_fetch_site(client, t, timeout) for t in targets)))
    fetched_at = (now or datetime.now(JST)).astimezone(JST)
    return {
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        # 合計は画面で、選んだサイトから出す（screen_design.md §3）
        "sites": sites,
    }

"""手元で Google を使わずに動かすためのダミー（GLANCE_FAKE_GOOGLE=1）。

数字はプロパティと「何時何分か」から決まる。同じ分に取り直すと同じ値になり、
時間が進むと分ごとの推移が左へずれていく。最後のプロパティ（エラー確認用）は、
リアルタイムを取ると必ず時間切れになる。
"""

import asyncio
import random
import time
from collections.abc import Callable

from glance.google.ga4 import (
    AccountSummary,
    BreakdownDimension,
    BreakdownRow,
    Ga4PermissionDenied,
    MinuteRow,
    PageRow,
    PropertyInfo,
    PropertySummary,
    Totals,
)

# (プロパティ ID, 名前, 1分あたりの PV の目安)
_PROPERTIES = [
    ("900000001", "LogiShift", 7),
    ("900000002", "TechShift", 4),
    ("900000003", "ConShift", 3),
    ("900000004", "FinShift", 2),
    ("900000005", "LeadHub", 5),
    ("900000099", "エラー確認用（リアルタイムが必ず時間切れ）", 1),
]
_ACCOUNTS = [
    ("800000001", "ダミーのアカウント 1", ["900000001", "900000002", "900000003"]),
    ("800000002", "ダミーのアカウント 2", ["900000004", "900000005", "900000099"]),
]
ERROR_PROPERTY_ID = "900000099"

_TOPICS = [
    "2024年問題",
    "WMS（倉庫管理システム）",
    "自動倉庫",
    "AGV と AMR の違い",
    "共同配送",
    "ラストワンマイル",
    "パレット輸送",
    "物流 DX",
    "3PL",
    "温度管理物流",
    "クロスドッキング",
    "モーダルシフト",
    "SCM",
    "在庫回転率",
    "ピッキングの効率化",
    "物流センターの立地",
    "ドローン配送",
    "トラックの積載率",
    "EC 物流",
    "返品物流",
    "フォークリフトの安全対策",
    "物流費の削減",
    "RFID",
    "需要予測",
]
_TITLE_FORMS = [
    "{t}とは？意味・仕組み・導入のポイントをわかりやすく解説",
    "{t}の最新動向まとめ",
    "{t}の事例10選",
    "{t}",
]


def _names() -> dict[str, tuple[str, int]]:
    return {pid: (name, rate) for pid, name, rate in _PROPERTIES}


class FakeGa4Client:
    def __init__(
        self,
        latency: tuple[float, float] = (0.1, 0.5),
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._latency = latency
        self._clock = clock

    async def _wait(self) -> None:
        low, high = self._latency
        if high > 0:
            await asyncio.sleep(random.uniform(low, high))

    def _property(self, property_id: str) -> tuple[str, int]:
        found = _names().get(property_id)
        if found is None:
            raise Ga4PermissionDenied(property_id)
        return found

    async def list_account_summaries(self) -> list[AccountSummary]:
        await self._wait()
        names = _names()
        return [
            AccountSummary(
                account_id=account_id,
                name=account_name,
                properties=[PropertySummary(pid, names[pid][0]) for pid in pids],
            )
            for account_id, account_name, pids in _ACCOUNTS
        ]

    async def get_property(self, property_id: str) -> PropertyInfo:
        await self._wait()
        name, _ = self._property(property_id)
        return PropertyInfo(property_id=property_id, name=name, time_zone="Asia/Tokyo")

    def _minutes(self, property_id: str) -> list[MinuteRow]:
        _, rate = self._property(property_id)
        now_minute = int(self._clock() // 60)
        rows = []
        for minutes_ago in range(30):
            rng = random.Random(f"{property_id}:{now_minute - minutes_ago}")
            page_views = max(0, round(rng.gauss(rate, rate * 0.5)))
            active_users = min(page_views, max(0, round(page_views * rng.uniform(0.5, 0.9))))
            rows.append(MinuteRow(minutes_ago, page_views, active_users))
        return rows

    def _check_error(self, property_id: str) -> None:
        if property_id == ERROR_PROPERTY_ID:
            raise TimeoutError(property_id)

    async def realtime_totals(self, property_id: str) -> tuple[Totals, Totals]:
        await self._wait()
        self._check_error(property_id)
        rows = self._minutes(property_id)
        recent = [r for r in rows if r.minutes_ago < 5]
        rng = random.Random(f"{property_id}:{int(self._clock() // 60)}:key")
        # 同じ人が何分にもまたがるので、30分・5分の人数は分ごとの人数の合計より少ない
        last_30 = Totals(
            page_views=sum(r.page_views for r in rows),
            active_users=round(sum(r.active_users for r in rows) * 0.6),
            key_events=rng.randint(0, 3),
        )
        last_5 = Totals(
            page_views=sum(r.page_views for r in recent),
            active_users=round(sum(r.active_users for r in recent) * 0.8),
            key_events=min(last_30.key_events, rng.randint(0, 1)),
        )
        return last_30, last_5

    async def realtime_per_minute(self, property_id: str) -> list[MinuteRow]:
        await self._wait()
        self._check_error(property_id)
        # 本物の API と同じく、値のない分は返さない
        return [r for r in self._minutes(property_id) if r.page_views > 0]

    async def realtime_top_pages(self, property_id: str, limit: int) -> list[PageRow]:
        await self._wait()
        self._check_error(property_id)
        name, _ = self._property(property_id)
        total = sum(r.page_views for r in self._minutes(property_id))
        rng = random.Random(f"{property_id}:{int(self._clock() // 60)}:pages")
        topics = rng.sample(_TOPICS, k=min(limit, len(_TOPICS)))
        rows = []
        remaining = total
        for rank, topic in enumerate(topics):
            share = max(1, round(remaining * rng.uniform(0.15, 0.3))) if remaining > 0 else 0
            if share == 0:
                break
            remaining -= share
            title = rng.choice(_TITLE_FORMS).format(t=topic) + f" | {name}"
            rows.append(PageRow(title, share, max(1, round(share * rng.uniform(0.6, 0.9)))))
        rows.sort(key=lambda r: r.page_views, reverse=True)
        return rows[:limit]

    async def realtime_breakdown(
        self, property_id: str, dimension: BreakdownDimension, limit: int
    ) -> list[BreakdownRow]:
        await self._wait()
        self._check_error(property_id)
        total = sum(r.page_views for r in self._minutes(property_id))
        rng = random.Random(f"{property_id}:{int(self._clock() // 60)}:{dimension}")
        if dimension == "deviceCategory":
            weights = {"mobile": rng.uniform(0.5, 0.75), "desktop": rng.uniform(0.2, 0.45), "tablet": rng.uniform(0.02, 0.07)}
        else:
            # 日本がほとんどで、Zaraz の判定のずれとボットで米国などが混ざる形にする
            weights = {
                "JP": rng.uniform(0.65, 0.85),
                "US": rng.uniform(0.08, 0.2),
                "CN": rng.uniform(0.0, 0.05),
                "SG": rng.uniform(0.0, 0.03),
                "KR": rng.uniform(0.0, 0.02),
                "(not set)": rng.uniform(0.0, 0.01),
            }
        scale = sum(weights.values())
        rows = []
        for key, weight in weights.items():
            page_views = round(total * weight / scale)
            if page_views > 0:
                rows.append(BreakdownRow(key, page_views, max(1, round(page_views * rng.uniform(0.6, 0.8)))))
        rows.sort(key=lambda r: r.page_views, reverse=True)
        return rows[:limit]

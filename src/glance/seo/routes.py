"""SEO の画面の API。今はデモ用の GET /api/demo/seo だけ（technical_design.md §6.3）。

本物の GET /api/seo は、2番目の段階で GSC・Bing のバッチを作るときに足す。応答の形は同じにする。
"""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from glance.errors import AppError
from glance.seo.demo import Engine, demo_seo
from glance.seo.periods import CompareName, PeriodError, PeriodName

router = APIRouter(prefix="/api")

JST = ZoneInfo("Asia/Tokyo")


@router.get("/demo/seo")
async def demo(
    engine: Engine = "google",
    period: PeriodName = "last_28_days",
    compare: CompareName = "previous_period",
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    # ログイン不要。ダミーの数字だけを返し、DB・Google・Bing・利用者のデータには触れない
    try:
        return demo_seo(engine, period, compare, datetime.now(JST).date(), start, end)
    except PeriodError as e:
        raise AppError(400, "invalid_period", str(e)) from e

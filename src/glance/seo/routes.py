"""SEO の画面の API。GET /api/seo（取り込んだ表から集計）と、デモ用の GET /api/demo/seo（technical_design.md §6.3）。

応答の形は同じ。
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from glance.auth.deps import CurrentUser, Db
from glance.errors import AppError
from glance.seo.demo import demo_seo
from glance.seo.periods import CompareName, Engine, PeriodError, PeriodName
from glance.seo.schemas import Seo
from glance.seo.service import seo_report

router = APIRouter(prefix="/api")

JST = ZoneInfo("Asia/Tokyo")


@router.get("/seo")
async def seo(
    db: Db,
    user: CurrentUser,
    engine: Engine = "google",
    period: PeriodName = "last_28_days",
    compare: CompareName = "previous_period",
    start: date | None = None,
    end: date | None = None,
) -> Seo:
    try:
        return await seo_report(db, user.tenant_id, engine, period, compare, datetime.now(JST).date(), start, end)
    except PeriodError as e:
        raise AppError(400, "invalid_period", str(e)) from e


@router.get("/demo/seo")
async def demo(
    engine: Engine = "google",
    period: PeriodName = "last_28_days",
    compare: CompareName = "previous_period",
    start: date | None = None,
    end: date | None = None,
) -> Seo:
    # ログイン不要。ダミーの数字だけを返し、DB・Google・Bing・利用者のデータには触れない
    try:
        return demo_seo(engine, period, compare, datetime.now(JST).date(), start, end)
    except PeriodError as e:
        raise AppError(400, "invalid_period", str(e)) from e

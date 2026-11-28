"""GET /api/realtime（technical_design.md §6.1）と、デモ用の GET /api/demo/realtime（§6.2）。"""

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from glance.auth.deps import CurrentUser, Db
from glance.db.models import Connection, Site
from glance.errors import AppError
from glance.google.fake import DEMO_SITES, FakeGa4Client
from glance.google.ga4 import ReauthRequired
from glance.realtime.service import SiteTarget, fetch_realtime
from glance.google.access import ga4_client

router = APIRouter(prefix="/api")


@router.get("/realtime")
async def realtime(request: Request, db: Db, user: CurrentUser) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(Site)
            .join(Connection, (Connection.site_id == Site.id) & (Connection.source == "ga4"))
            .where(Site.tenant_id == user.tenant_id, Site.ga4_property_id.is_not(None))
            .order_by(Site.sort_order, Site.id)
        )
    ).scalars()
    targets = [SiteTarget(site_id=s.id, name=s.name, property_id=s.ga4_property_id or "") for s in rows]
    client = ga4_client(request, user)
    try:
        return await fetch_realtime(client, targets, timeout=request.app.state.realtime_timeout)
    except ReauthRequired as e:
        raise AppError(401, "reauth_required", "Google の許可が切れました。ログインし直してください") from e


# デモはログイン不要。ダミーの数字だけを返し、DB・Google・利用者のデータには触れない
_demo_client = FakeGa4Client()
_demo_targets = [SiteTarget(site_id=i + 1, name=name, property_id=pid) for i, (pid, name) in enumerate(DEMO_SITES)]


@router.get("/demo/realtime")
async def demo_realtime(request: Request) -> dict[str, Any]:
    return await fetch_realtime(_demo_client, _demo_targets, timeout=request.app.state.realtime_timeout)

"""サイト設定の API（technical_design.md §6）と、デモ用の GET /api/demo/sites ほか（§6.4）。

サイトは、ログイン中の利用者の顧客のものだけを扱う。
"""

from typing import Annotated

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select

from glance.auth.deps import CurrentUser, Db
from glance.db.models import Connection, Site, User
from glance.errors import AppError
from glance.sites import demo
from glance.google.ga4 import Ga4Client, Ga4PermissionDenied, ReauthRequired

router = APIRouter(prefix="/api")

PropertyId = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,20}$")]
SiteName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SiteLinks(BaseModel):
    """Search Console・Bing の紐づけ先。紐づけていないものは None。"""

    gsc_site_url: str | None
    bing_site_url: str | None


class SiteOut(BaseModel):
    id: int
    name: str
    sort_order: int
    timezone: str
    ga4_property_id: str | None
    # Search Console・Bing の紐づけ。紐づけの API があるときだけ返す（今はデモだけ。本物は None）
    links: SiteLinks | None = None


class SiteCreate(BaseModel):
    property_id: PropertyId


class SiteUpdate(BaseModel):
    name: SiteName | None = None
    # 0 から数えた並びの位置。範囲の外なら、先頭か末尾に置く
    position: int | None = Field(default=None, ge=0)


class SearchConsoleMatch(BaseModel):
    """GA4 のプロパティと同じドメインの Search Console のサイト（site_url。見つからなければ None）と、選べるサイト。"""

    site_url: str | None
    candidates: list[str]


class PropertyOut(BaseModel):
    property_id: str
    name: str
    added: bool
    # 追加するときに一緒に紐づける Search Console のサイト。紐づけの API があるときだけ返す（今はデモだけ）
    search_console: SearchConsoleMatch | None = None


class BingSitesOut(BaseModel):
    key_saved: bool  # Bing の API キーを保存済みか（キーそのものは返さない）
    sites: list[str]  # そのキーで見られる Bing のサイト


class AccountOut(BaseModel):
    account_id: str
    name: str
    properties: list[PropertyOut]


def ga4_client(request: Request, user: User) -> Ga4Client:
    try:
        return request.app.state.ga4_factory(user)
    except ReauthRequired as e:
        # 更新トークンを持っていない（フェイクのログインの後など）。Google でログインし直してもらう
        raise AppError(401, "reauth_required", "Google の許可が切れました。ログインし直してください") from e


async def _sites(db: Db, tenant_id: int) -> list[Site]:
    return list(
        (await db.execute(select(Site).where(Site.tenant_id == tenant_id).order_by(Site.sort_order, Site.id)))
        .scalars()
        .all()
    )


async def _site(db: Db, tenant_id: int, site_id: int) -> Site:
    site = await db.get(Site, site_id)
    if site is None or site.tenant_id != tenant_id:
        raise AppError(404, "not_found", "サイトが見つかりません")
    return site


def _out(site: Site) -> SiteOut:
    return SiteOut(
        id=site.id,
        name=site.name,
        sort_order=site.sort_order,
        timezone=site.timezone,
        ga4_property_id=site.ga4_property_id,
    )


def _renumber(sites: list[Site]) -> None:
    for i, site in enumerate(sites):
        site.sort_order = i


@router.get("/ga4/properties")
async def list_properties(request: Request, db: Db, user: CurrentUser) -> list[AccountOut]:
    client = ga4_client(request, user)
    try:
        accounts = await client.list_account_summaries()
    except ReauthRequired as e:
        raise AppError(401, "reauth_required", "Google の許可が切れました。ログインし直してください") from e
    added = {s.ga4_property_id for s in await _sites(db, user.tenant_id)}
    return [
        AccountOut(
            account_id=a.account_id,
            name=a.name,
            properties=[PropertyOut(property_id=p.property_id, name=p.name, added=p.property_id in added) for p in a.properties],
        )
        for a in accounts
    ]


@router.get("/sites")
async def list_sites(db: Db, user: CurrentUser) -> list[SiteOut]:
    return [_out(s) for s in await _sites(db, user.tenant_id)]


@router.post("/sites", status_code=201)
async def create_site(body: SiteCreate, request: Request, db: Db, user: CurrentUser) -> SiteOut:
    exists = await db.scalar(
        select(Site.id).where(Site.tenant_id == user.tenant_id, Site.ga4_property_id == body.property_id)
    )
    if exists is not None:
        raise AppError(409, "already_added", "このプロパティは追加済みです")

    client = ga4_client(request, user)
    try:
        info = await client.get_property(body.property_id)
    except Ga4PermissionDenied as e:
        raise AppError(403, "permission_denied", "このプロパティを見る権限がありません") from e
    except ReauthRequired as e:
        raise AppError(401, "reauth_required", "Google の許可が切れました。ログインし直してください") from e

    next_order = await db.scalar(
        select(func.coalesce(func.max(Site.sort_order) + 1, 0)).where(Site.tenant_id == user.tenant_id)
    )
    site = Site(
        tenant_id=user.tenant_id,
        name=info.name,
        sort_order=next_order,
        timezone=info.time_zone,
        ga4_property_id=info.property_id,
    )
    db.add(site)
    await db.flush()
    db.add(Connection(site_id=site.id, source="ga4", auth_method="google", user_id=user.id))
    await db.commit()
    return _out(site)


@router.patch("/sites/{site_id}")
async def update_site(site_id: int, body: SiteUpdate, db: Db, user: CurrentUser) -> SiteOut:
    site = await _site(db, user.tenant_id, site_id)
    if body.name is not None:
        site.name = body.name
    if body.position is not None:
        sites = [s for s in await _sites(db, user.tenant_id) if s.id != site.id]
        sites.insert(min(body.position, len(sites)), site)
        _renumber(sites)
    await db.commit()
    return _out(site)


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, db: Db, user: CurrentUser) -> Response:
    site = await _site(db, user.tenant_id, site_id)
    await db.delete(site)
    await db.flush()
    _renumber(await _sites(db, user.tenant_id))
    await db.commit()
    return Response(status_code=204)


# デモ（ログイン不要。見るだけ）。ダミーだけを返し、DB・Google・Bing・利用者のデータには触れない（glance/sites/demo.py）。
# 書き込みの API はデモにはない（画面でボタンを押せなくする）


@router.get("/demo/sites")
async def demo_sites() -> list[SiteOut]:
    return [SiteOut.model_validate(site) for site in demo.sites()]


@router.get("/demo/ga4/properties")
async def demo_properties() -> list[AccountOut]:
    return [AccountOut.model_validate(account) for account in demo.accounts()]


@router.get("/demo/gsc/sites")
async def demo_gsc_sites() -> list[str]:
    return demo.GSC_SITES


@router.get("/demo/bing/sites")
async def demo_bing_sites() -> BingSitesOut:
    return BingSitesOut.model_validate(demo.bing())

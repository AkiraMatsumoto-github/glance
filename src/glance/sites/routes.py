"""サイト設定の API（technical_design.md §6・§6.4）と、デモ用の GET /api/demo/sites ほか。

サイトは、ログイン中の利用者の顧客のものだけを扱う。Search Console・Bing の紐づけは glance.sites.links。
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select

from glance.auth.deps import CurrentUser, Db
from glance.db.models import Connection, Site
from glance.errors import AppError
from glance.google.access import google_client, reauth_error
from glance.google.client import (
    GooglePermissionDenied,
    GoogleQuotaExceeded,
    GoogleUnavailable,
    GscApiDisabled,
    ReauthRequired,
)
from glance.sites import demo
from glance.bing.routes import BingKeyOut
from glance.sites.common import tenant_site
from glance.sites.gsc import ensure_gsc_site, match_gsc_site
from glance.sites.links import GscChoiceOut, set_link

router = APIRouter(prefix="/api")

# 「サイトを追加」で、同じドメインの Search Console のサイトを探すために GA4 の Admin API を同時に呼ぶ数の上限
# （プロパティの多いアカウントで、上限を使い切らないため）
STREAM_LOOKUPS = 5

PropertyId = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,20}$")]
SiteName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SiteLinks(BaseModel):
    """Search Console・Bing の紐づけ先と、Bing で使うキー。紐づけていないものは None。"""

    gsc_site_url: str | None
    bing_site_url: str | None
    bing_key_id: int | None


class SiteOut(BaseModel):
    id: int
    name: str
    ga4_property_id: str | None
    links: SiteLinks


class SiteCreate(BaseModel):
    property_id: PropertyId
    # 一緒に紐づける Search Console のサイト（screen_design.md §4）。None なら紐づけない
    gsc_site_url: str | None = None


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
    # 追加するときに一緒に紐づける Search Console のサイト。追加済みのとき、
    # Search Console のサイトの一覧を取れないとき（API を有効にしていないなど）は None
    search_console: SearchConsoleMatch | None


class AccountOut(BaseModel):
    account_id: str
    name: str
    properties: list[PropertyOut]


async def _sites(db: Db, tenant_id: int) -> list[Site]:
    return list(
        (await db.execute(select(Site).where(Site.tenant_id == tenant_id).order_by(Site.sort_order, Site.id)))
        .scalars()
        .all()
    )


async def _links(db: Db, site_ids: list[int]) -> dict[int, SiteLinks]:
    """サイトごとの Search Console・Bing の紐づけ（接続設定の行から）。"""
    links = {site_id: SiteLinks(gsc_site_url=None, bing_site_url=None, bing_key_id=None) for site_id in site_ids}
    rows = await db.scalars(
        select(Connection).where(Connection.site_id.in_(site_ids), Connection.source.in_(["gsc", "bing"]))
    )
    for c in rows:
        if c.source == "gsc":
            links[c.site_id].gsc_site_url = c.target
        else:
            links[c.site_id].bing_site_url = c.target
            links[c.site_id].bing_key_id = c.bing_key_id
    return links


def _out(site: Site, links: SiteLinks) -> SiteOut:
    return SiteOut(
        id=site.id,
        name=site.name,
        ga4_property_id=site.ga4_property_id,
        links=links,
    )


def _renumber(sites: list[Site]) -> None:
    for i, site in enumerate(sites):
        site.sort_order = i


@router.get("/ga4/properties")
async def list_properties(request: Request, db: Db, user: CurrentUser) -> list[AccountOut]:
    client = google_client(request, user)
    try:
        accounts = await client.list_account_summaries()
    except ReauthRequired as e:
        raise reauth_error() from e
    added = {s.ga4_property_id for s in await _sites(db, user.tenant_id)}
    candidates = [p.property_id for a in accounts for p in a.properties if p.property_id not in added]

    # 追加していないプロパティに、同じドメインの Search Console のサイトを選んでおく（data_sources.md §3）。
    # Search Console のサイトの一覧を取れなくても、GA4 のプロパティの追加はできるようにする
    gsc: list[str] | None
    try:
        gsc = await client.list_gsc_sites()
    except (GscApiDisabled, GooglePermissionDenied, GoogleQuotaExceeded, GoogleUnavailable):
        gsc = None
    except ReauthRequired as e:
        raise reauth_error() from e
    matches: dict[str, SearchConsoleMatch] = {}
    if gsc is not None:
        slots = asyncio.Semaphore(STREAM_LOOKUPS)

        async def hosts_of(property_id: str) -> list[str]:
            async with slots:
                return await client.web_stream_hosts(property_id)

        # 取れないプロパティ（権限・上限・接続の失敗）は、おすすめなしにする
        hosts = await asyncio.gather(*(hosts_of(pid) for pid in candidates), return_exceptions=True)
        for pid, found in zip(candidates, hosts, strict=True):
            site_url = match_gsc_site(found, gsc) if isinstance(found, list) else None
            matches[pid] = SearchConsoleMatch(site_url=site_url, candidates=gsc)
    return [
        AccountOut(
            account_id=a.account_id,
            name=a.name,
            properties=[
                PropertyOut(
                    property_id=p.property_id,
                    name=p.name,
                    added=p.property_id in added,
                    search_console=matches.get(p.property_id),
                )
                for p in a.properties
            ],
        )
        for a in accounts
    ]


@router.get("/sites")
async def list_sites(db: Db, user: CurrentUser) -> list[SiteOut]:
    sites = await _sites(db, user.tenant_id)
    links = await _links(db, [s.id for s in sites])
    return [_out(s, links[s.id]) for s in sites]


@router.post("/sites", status_code=201)
async def create_site(body: SiteCreate, request: Request, db: Db, user: CurrentUser) -> SiteOut:
    exists = await db.scalar(
        select(Site.id).where(Site.tenant_id == user.tenant_id, Site.ga4_property_id == body.property_id)
    )
    if exists is not None:
        raise AppError(409, "already_added", "このプロパティは追加済みです")

    client = google_client(request, user)
    try:
        info = await client.get_property(body.property_id)
    except GooglePermissionDenied as e:
        raise AppError(403, "permission_denied", "このプロパティを見る権限がありません") from e
    except ReauthRequired as e:
        raise reauth_error() from e
    if body.gsc_site_url is not None:
        await ensure_gsc_site(client, body.gsc_site_url)

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
    if body.gsc_site_url is not None:
        await set_link(db, site.id, "gsc", body.gsc_site_url, auth_method="google", user_id=user.id)
    await db.commit()
    return _out(site, (await _links(db, [site.id]))[site.id])


@router.patch("/sites/{site_id}")
async def update_site(site_id: int, body: SiteUpdate, db: Db, user: CurrentUser) -> SiteOut:
    site = await tenant_site(db, user.tenant_id, site_id)
    if body.name is not None:
        site.name = body.name
    if body.position is not None:
        sites = [s for s in await _sites(db, user.tenant_id) if s.id != site.id]
        sites.insert(min(body.position, len(sites)), site)
        _renumber(sites)
    await db.commit()
    return _out(site, (await _links(db, [site.id]))[site.id])


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, db: Db, user: CurrentUser) -> Response:
    # 接続設定も消える。取り込んだ数字のテーブルも、サイトと一緒に消す（database_design.md §2）
    site = await tenant_site(db, user.tenant_id, site_id)
    await db.delete(site)
    await db.flush()
    _renumber(await _sites(db, user.tenant_id))
    await db.commit()
    return Response(status_code=204)


# デモ（ログイン不要。見るだけ）。ダミーだけを返し、DB・Google・Bing・利用者のデータには触れない（glance/sites/demo.py）。
# 書き込みの API はデモにはない（画面でボタンを押せなくする）。応答の形は本物と同じ


@router.get("/demo/sites")
async def demo_sites() -> list[SiteOut]:
    return [SiteOut.model_validate(site) for site in demo.sites()]


@router.get("/demo/ga4/properties")
async def demo_properties() -> list[AccountOut]:
    return [AccountOut.model_validate(account) for account in demo.accounts()]


@router.get("/demo/sites/{site_id}/gsc")
async def demo_gsc_choice(site_id: int) -> GscChoiceOut:
    return GscChoiceOut.model_validate(demo.gsc_choice(site_id))


@router.get("/demo/bing/keys")
async def demo_bing_keys() -> list[BingKeyOut]:
    return [BingKeyOut.model_validate(key) for key in demo.BING_KEYS]


@router.get("/demo/bing/keys/{key_id}/sites")
async def demo_bing_key_sites(key_id: int) -> list[str]:
    return demo.BING_SITES

"""サイトと Search Console・Bing の紐づけの API（technical_design.md §6.4、screen_design.md §4）。

紐づけは接続設定（connections）の行で持つ。行があれば紐づけていて、target が紐づけ先（サイトの URL）。
どの認証で呼ぶか（Google は利用者、Bing はキー）も同じ行に持つ。
紐づけを外しても取り込んだ数字は残す。紐づけ先を別のサイトに変えたら、前のサイトの数字を消して取り直す。
Search Console のサイトの選び方は glance/sites/gsc.py、Bing のキーの API は glance/bing/routes.py。
"""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select

from glance.auth.deps import CurrentUser, Db
from glance.bing.routes import bing_sites, key_cipher, tenant_key
from glance.db.models import (
    BingCrawlDaily,
    BingPageWeekly,
    BingSiteDaily,
    Connection,
    GscPage,
    GscQueryPage,
    GscSite,
    SitemapUrl,
    SyncRun,
)
from glance.errors import AppError
from glance.google.access import google_client
from glance.sites.common import tenant_site
from glance.sites.gsc import ensure_gsc_site, gsc_sites, suggested_gsc_site

router = APIRouter(prefix="/api")

# 紐づけ先を変えたときに消す、取り込んだ数字（ソースごと）。サイトマップは Search Console のプロパティから読む
DATA_TABLES = {
    "gsc": [GscSite, GscPage, GscQueryPage, SitemapUrl],
    "bing": [BingSiteDaily, BingPageWeekly, BingCrawlDaily],
}


async def set_link(db: Db, site_id: int, source: str, target: str | None, **auth: object) -> None:
    """紐づける（target と認証を書く）か、外す（target が None なら行を消す）。

    前に取り込んだ先と違う先に紐づけるときは、前の先の数字と取得ログを消す（次の取り込みで、新しい先の過去分から取る）。
    外すだけなら数字は残す。同じ先に紐づけ直したら、続きから取る。
    """
    connection = await db.scalar(select(Connection).where(Connection.site_id == site_id, Connection.source == source))
    if target is None:
        if connection is not None:
            await db.delete(connection)
        return
    fetched = await db.scalar(
        select(SyncRun.target)
        .where(SyncRun.site_id == site_id, SyncRun.source == source, SyncRun.target.is_not(None))
        .order_by(SyncRun.id.desc())
        .limit(1)
    )
    if fetched is not None and fetched != target:
        for model in DATA_TABLES[source]:
            await db.execute(delete(model).where(model.site_id == site_id))  # type: ignore[attr-defined]
        await db.execute(delete(SyncRun).where(SyncRun.site_id == site_id, SyncRun.source == source))
    if connection is None:
        connection = Connection(site_id=site_id, source=source)
        db.add(connection)
    connection.target = target
    for name, value in auth.items():
        setattr(connection, name, value)


# --- Search Console ---------------------------------------------------------------------


class GscChoiceOut(BaseModel):
    current: str | None  # いま紐づけているサイト
    suggested: str | None  # 同じドメインのサイト（data_sources.md §3）
    candidates: list[str]  # ログインしたアカウントが見られるサイト


class GscLinkIn(BaseModel):
    site_url: str | None  # None で紐づけを外す


async def _target(db: Db, site_id: int, source: str) -> str | None:
    return await db.scalar(select(Connection.target).where(Connection.site_id == site_id, Connection.source == source))


@router.get("/sites/{site_id}/gsc")
async def gsc_choice(site_id: int, request: Request, db: Db, user: CurrentUser) -> GscChoiceOut:
    site = await tenant_site(db, user.tenant_id, site_id)
    client = google_client(request, user)
    candidates = await gsc_sites(client)
    suggested = await suggested_gsc_site(client, site.ga4_property_id, candidates)
    return GscChoiceOut(current=await _target(db, site.id, "gsc"), suggested=suggested, candidates=candidates)


@router.put("/sites/{site_id}/gsc", status_code=204)
async def link_gsc(site_id: int, body: GscLinkIn, request: Request, db: Db, user: CurrentUser) -> Response:
    site = await tenant_site(db, user.tenant_id, site_id)
    if body.site_url is not None:
        await ensure_gsc_site(google_client(request, user), body.site_url)
    # 保存した利用者の更新トークンで取り込む
    await set_link(db, site.id, "gsc", body.site_url, auth_method="google", user_id=user.id, bing_key_id=None)
    await db.commit()
    return Response(status_code=204)


# --- Bing --------------------------------------------------------------------------------


class BingLinkIn(BaseModel):
    key_id: int | None = None
    site_url: str | None  # None で紐づけを外す


@router.put("/sites/{site_id}/bing", status_code=204)
async def link_bing(site_id: int, body: BingLinkIn, request: Request, db: Db, user: CurrentUser) -> Response:
    site = await tenant_site(db, user.tenant_id, site_id)
    key_id = None
    if body.site_url is not None:
        if body.key_id is None:
            raise AppError(400, "key_required", "Bing のキーを選んでください")
        key = await tenant_key(db, user.tenant_id, body.key_id)
        if body.site_url not in await bing_sites(request, key_cipher(request).decrypt(key.key_encrypted)):
            raise AppError(400, "unknown_bing_site", "このキーで見られない Bing のサイトです")
        key_id = key.id
    await set_link(db, site.id, "bing", body.site_url, auth_method="api_key", user_id=None, bing_key_id=key_id)
    await db.commit()
    return Response(status_code=204)

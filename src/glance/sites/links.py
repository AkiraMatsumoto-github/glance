"""サイトと Search Console・Bing の紐づけの API（technical_design.md §6.4、screen_design.md §4）。

紐づけは接続設定（connections）の行で持つ。行があれば紐づけていて、target が紐づけ先（サイトの URL）。
どの認証で呼ぶか（Google は利用者、Bing はキー）も同じ行に持つ。
Bing のキーは顧客ごとに bing_keys に暗号化して持ち、画面には名前と末尾4文字だけを出す。
紐づけを外しても取り込んだ数字は残す。紐づけ先を別のサイトに変えたら、前のサイトの数字を消して取り直す。
"""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, StringConstraints
from sqlalchemy import delete, func, select

from glance.auth.crypto import TokenCipher
from glance.auth.deps import CurrentUser, Db
from glance.bing.client import BingClient, BingKeyInvalid, BingUnavailable
from glance.db.models import (
    BingCrawlDaily,
    BingKey,
    BingPageWeekly,
    BingSiteDaily,
    Connection,
    GscPage,
    GscQueryPage,
    GscSite,
    Site,
    SitemapUrl,
    SyncRun,
)
from glance.errors import AppError
from glance.google.access import google_client, reauth_error
from glance.google.client import (
    GoogleClient,
    GooglePermissionDenied,
    GoogleQuotaExceeded,
    GoogleUnavailable,
    GscApiDisabled,
    ReauthRequired,
)

router = APIRouter(prefix="/api")

KeyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ApiKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=200)]

# 紐づけ先を変えたときに消す、取り込んだ数字（ソースごと）。サイトマップは Search Console のプロパティから読む
DATA_TABLES = {
    "gsc": [GscSite, GscPage, GscQueryPage, SitemapUrl],
    "bing": [BingSiteDaily, BingPageWeekly, BingCrawlDaily],
}


# --- Search Console のサイトの選び方 -------------------------------------------------


def _bare(host: str) -> str:
    return host.lower().removeprefix("www.")


def match_gsc_site(hosts: list[str], sites: list[str]) -> str | None:
    """GA4 のホストと同じドメインの Search Console のサイト（data_sources.md §3）。

    ドメインのプロパティ（sc-domain:）があればそれ（いくつか合うときは、いちばん細かいドメイン）。
    なければ、同じホスト（www. の有無は問わない）の URL のプロパティが1つだけあるときにそれ。どちらもなければ None。
    """
    names = {host.lower() for host in hosts}
    domains = [
        site
        for site in sites
        if site.startswith("sc-domain:")
        and any(name == site.removeprefix("sc-domain:") or name.endswith("." + site.removeprefix("sc-domain:")) for name in names)
    ]
    if domains:
        return max(domains, key=len)
    bare = {_bare(name) for name in names}
    prefixes = [site for site in sites if not site.startswith("sc-domain:") and _bare(urlsplit(site).hostname or "") in bare]
    return prefixes[0] if len(prefixes) == 1 else None


# --- 共通の部品 --------------------------------------------------------------------------


async def tenant_site(db: Db, tenant_id: int, site_id: int) -> Site:
    """ログイン中の利用者の顧客のサイト。ほかの顧客のサイトは、無いのと同じに扱う。"""
    site = await db.get(Site, site_id)
    if site is None or site.tenant_id != tenant_id:
        raise AppError(404, "not_found", "サイトが見つかりません")
    return site


async def gsc_sites(client: GoogleClient) -> list[str]:
    """ログインしたアカウントが見られる Search Console のサイト。取れなければ、理由を画面に出せるエラーにする。"""
    try:
        return await client.list_gsc_sites()
    except ReauthRequired as e:
        raise reauth_error() from e
    except GscApiDisabled as e:
        raise AppError(
            503, "gsc_api_disabled", "Search Console API が有効になっていません。GCP のプロジェクトで有効にしてください"
        ) from e
    except GooglePermissionDenied as e:
        raise AppError(403, "permission_denied", "Search Console のサイトの一覧を見る権限がありません") from e
    except GoogleQuotaExceeded as e:
        raise AppError(429, "gsc_quota", "Search Console の呼び出しの上限に当たりました。少し待ってから試してください") from e
    except GoogleUnavailable as e:
        raise AppError(502, "gsc_unavailable", "Search Console に接続できませんでした。時間をおいて試してください") from e


async def ensure_gsc_site(client: GoogleClient, site_url: str) -> None:
    """紐づけようとしている Search Console のサイトが、ログインしたアカウントで見られるか確かめる。"""
    if site_url not in await gsc_sites(client):
        raise AppError(400, "unknown_gsc_site", "このアカウントで見られない Search Console のサイトです")


async def suggested_gsc_site(client: GoogleClient, property_id: str | None, sites: list[str]) -> str | None:
    """GA4 のプロパティと同じドメインのサイト。取れなければ（上限・接続の失敗も）おすすめなしにする。"""
    if not property_id:
        return None
    try:
        hosts = await client.web_stream_hosts(property_id)
    except (GooglePermissionDenied, GoogleQuotaExceeded, GoogleUnavailable):
        return None
    except ReauthRequired as e:
        raise reauth_error() from e
    return match_gsc_site(hosts, sites)


def _cipher(request: Request) -> TokenCipher:
    cipher: TokenCipher | None = request.app.state.cipher
    if cipher is None:
        raise AppError(500, "no_token_key", "暗号化の鍵（GLANCE_TOKEN_KEY）が設定されていません")
    return cipher


async def _bing_sites(request: Request, api_key: str) -> list[str]:
    client: BingClient = request.app.state.bing_client
    try:
        return await client.list_sites(api_key)
    except BingKeyInvalid as e:
        raise AppError(400, "invalid_bing_key", "Bing の API キーが正しくありません。入れ直してください") from e
    except BingUnavailable as e:
        raise AppError(502, "bing_unavailable", "Bing に接続できませんでした。時間をおいて試してください") from e


async def _key(db: Db, tenant_id: int, key_id: int) -> BingKey:
    key = await db.get(BingKey, key_id)
    if key is None or key.tenant_id != tenant_id:
        raise AppError(404, "not_found", "Bing のキーが見つかりません")
    return key


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


@router.put("/sites/{site_id}/gsc")
async def link_gsc(site_id: int, body: GscLinkIn, request: Request, db: Db, user: CurrentUser) -> dict[str, str | None]:
    site = await tenant_site(db, user.tenant_id, site_id)
    if body.site_url is not None:
        await ensure_gsc_site(google_client(request, user), body.site_url)
    # 保存した利用者の更新トークンで取り込む
    await set_link(db, site.id, "gsc", body.site_url, auth_method="google", user_id=user.id, bing_key_id=None)
    await db.commit()
    return {"gsc_site_url": body.site_url}


# --- Bing --------------------------------------------------------------------------------


class BingKeyOut(BaseModel):
    id: int
    name: str
    last4: str  # キーそのものは返さない


class BingKeyCreate(BaseModel):
    name: KeyName
    key: ApiKey


class BingKeyUpdate(BaseModel):
    key: ApiKey


class BingLinkIn(BaseModel):
    key_id: int | None = None
    site_url: str | None  # None で紐づけを外す


def _key_out(key: BingKey) -> BingKeyOut:
    return BingKeyOut(id=key.id, name=key.name, last4=key.last4)


@router.get("/bing/keys")
async def list_bing_keys(db: Db, user: CurrentUser) -> list[BingKeyOut]:
    keys = await db.scalars(select(BingKey).where(BingKey.tenant_id == user.tenant_id).order_by(BingKey.id))
    return [_key_out(k) for k in keys]


@router.post("/bing/keys", status_code=201)
async def create_bing_key(body: BingKeyCreate, request: Request, db: Db, user: CurrentUser) -> BingKeyOut:
    taken = await db.scalar(select(BingKey.id).where(BingKey.tenant_id == user.tenant_id, BingKey.name == body.name))
    if taken is not None:
        raise AppError(409, "name_taken", "同じ名前のキーがあります。別の名前にしてください")
    # 使えるキーかを、保存する前に確かめる
    await _bing_sites(request, body.key)
    key = BingKey(
        tenant_id=user.tenant_id, name=body.name, key_encrypted=_cipher(request).encrypt(body.key), last4=body.key[-4:]
    )
    db.add(key)
    await db.commit()
    return _key_out(key)


@router.put("/bing/keys/{key_id}")
async def update_bing_key(key_id: int, body: BingKeyUpdate, request: Request, db: Db, user: CurrentUser) -> BingKeyOut:
    # 入れ直し。このキーを使う全サイトに効く
    key = await _key(db, user.tenant_id, key_id)
    await _bing_sites(request, body.key)
    key.key_encrypted = _cipher(request).encrypt(body.key)
    key.last4 = body.key[-4:]
    key.updated_at = func.now()
    await db.commit()
    await db.refresh(key)
    return _key_out(key)


@router.get("/bing/keys/{key_id}/sites")
async def bing_key_sites(key_id: int, request: Request, db: Db, user: CurrentUser) -> list[str]:
    key = await _key(db, user.tenant_id, key_id)
    return await _bing_sites(request, _cipher(request).decrypt(key.key_encrypted))


@router.put("/sites/{site_id}/bing")
async def link_bing(site_id: int, body: BingLinkIn, request: Request, db: Db, user: CurrentUser) -> dict[str, object]:
    site = await tenant_site(db, user.tenant_id, site_id)
    key_id = None
    if body.site_url is not None:
        if body.key_id is None:
            raise AppError(400, "key_required", "Bing のキーを選んでください")
        key = await _key(db, user.tenant_id, body.key_id)
        if body.site_url not in await _bing_sites(request, _cipher(request).decrypt(key.key_encrypted)):
            raise AppError(400, "unknown_bing_site", "このキーで見られない Bing のサイトです")
        key_id = key.id
    await set_link(db, site.id, "bing", body.site_url, auth_method="api_key", user_id=None, bing_key_id=key_id)
    await db.commit()
    return {"bing_site_url": body.site_url, "bing_key_id": key_id}

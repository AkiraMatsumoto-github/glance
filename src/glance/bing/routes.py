"""Bing の API キーの API（technical_design.md §6.4）。

キーは顧客ごとに bing_keys に暗号化して持ち、画面には名前と末尾4文字だけを出す。保存の前に、使えるキーか確かめる。
サイトの紐づけ（PUT /api/sites/{id}/bing）は glance/sites/links.py。
"""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select

from glance.auth.crypto import TokenCipher
from glance.auth.deps import CurrentUser, Db
from glance.bing.client import BingClient, BingKeyInvalid, BingUnavailable
from glance.db.models import BingKey
from glance.errors import AppError

router = APIRouter(prefix="/api")

KeyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ApiKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=200)]


def key_cipher(request: Request) -> TokenCipher:
    cipher: TokenCipher | None = request.app.state.cipher
    if cipher is None:
        raise AppError(500, "no_token_key", "暗号化の鍵（GLANCE_TOKEN_KEY）が設定されていません")
    return cipher


async def bing_sites(request: Request, api_key: str) -> list[str]:
    client: BingClient = request.app.state.bing_client
    try:
        return await client.list_sites(api_key)
    except BingKeyInvalid as e:
        raise AppError(400, "invalid_bing_key", "Bing の API キーが正しくありません。入れ直してください") from e
    except BingUnavailable as e:
        raise AppError(502, "bing_unavailable", "Bing に接続できませんでした。時間をおいて試してください") from e


async def tenant_key(db: Db, tenant_id: int, key_id: int) -> BingKey:
    key = await db.get(BingKey, key_id)
    if key is None or key.tenant_id != tenant_id:
        raise AppError(404, "not_found", "Bing のキーが見つかりません")
    return key


class BingKeyOut(BaseModel):
    id: int
    name: str
    last4: str  # キーそのものは返さない


class BingKeyCreate(BaseModel):
    name: KeyName
    key: ApiKey


class BingKeyUpdate(BaseModel):
    key: ApiKey


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
    await bing_sites(request, body.key)
    key = BingKey(
        tenant_id=user.tenant_id, name=body.name, key_encrypted=key_cipher(request).encrypt(body.key), last4=body.key[-4:]
    )
    db.add(key)
    await db.commit()
    return _key_out(key)


@router.put("/bing/keys/{key_id}")
async def update_bing_key(key_id: int, body: BingKeyUpdate, request: Request, db: Db, user: CurrentUser) -> BingKeyOut:
    # 入れ直し。このキーを使う全サイトに効く
    key = await tenant_key(db, user.tenant_id, key_id)
    await bing_sites(request, body.key)
    key.key_encrypted = key_cipher(request).encrypt(body.key)
    key.last4 = body.key[-4:]
    key.updated_at = func.now()
    await db.commit()
    await db.refresh(key)
    return _key_out(key)


@router.get("/bing/keys/{key_id}/sites")
async def bing_key_sites(key_id: int, request: Request, db: Db, user: CurrentUser) -> list[str]:
    key = await tenant_key(db, user.tenant_id, key_id)
    return await bing_sites(request, key_cipher(request).decrypt(key.key_encrypted))

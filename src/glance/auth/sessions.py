"""ログインのセッション（technical_design.md §4）。

ランダムな ID をクッキーに入れ、DB にはそのハッシュだけを入れる。期限は30日。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from glance.db.models import LoginSession, Tenant, User

COOKIE_NAME = "glance_session"
SESSION_DAYS = 30


def hash_session_id(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_session(db: AsyncSession, user: User) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            id_hash=hash_session_id(raw),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=SESSION_DAYS),
        )
    )
    await db.commit()
    return raw


async def find_user(db: AsyncSession, raw: str) -> User | None:
    row = (
        await db.execute(
            select(LoginSession, User)
            .join(User, User.id == LoginSession.user_id)
            .where(LoginSession.id_hash == hash_session_id(raw))
        )
    ).first()
    if row is None:
        return None
    session, user = row
    if session.expires_at <= datetime.now(UTC):
        await db.delete(session)
        await db.commit()
        return None
    return user


async def end_sessions(db: AsyncSession, user: User) -> None:
    """その人のセッションを全部消す（全部の端末からログアウトさせる）。"""
    await db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    await db.commit()


async def delete_session(db: AsyncSession, raw: str) -> None:
    await db.execute(delete(LoginSession).where(LoginSession.id_hash == hash_session_id(raw)))
    await db.commit()


def set_session_cookie(response: Response, raw: str, secure: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=secure, samesite="lax")


async def upsert_user(db: AsyncSession, google_sub: str, email: str) -> User:
    """ログインした人を利用者として作る（いれば更新する）。顧客は1番目の段階では自社の1つだけ。"""
    user = (await db.execute(select(User).where(User.google_sub == google_sub))).scalar_one_or_none()
    if user is None:
        tenant_id = (await db.execute(select(Tenant.id).order_by(Tenant.id).limit(1))).scalar_one()
        user = User(tenant_id=tenant_id, google_sub=google_sub, email=email)
        db.add(user)
    user.email = email
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return user

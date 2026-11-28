"""ログインのセッション（technical_design.md §4）。

ランダムな ID をクッキー（glance/auth/cookies.py）に入れ、DB にはそのハッシュだけを入れる。期限は30日。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from glance.db.models import LoginSession, Tenant, User

SESSION_DAYS = 30
SESSION_SECONDS = SESSION_DAYS * 24 * 60 * 60


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


async def upsert_user(db: AsyncSession, google_sub: str, email: str) -> User:
    """ログインした人を利用者として作る（いれば更新する）。

    初めての人には、その人だけの顧客を作る。サイト・連携・Bing のキー・取り込んだ数字は顧客ごとに分けてあるので、
    アカウントごとに別々になり、ほかの人のものは見えない（2026-11-28 利用者の決定）。
    会社で共有する形（招待）は、外販の準備のときに作る（roadmap.md §3.6）。
    """
    user = (await db.execute(select(User).where(User.google_sub == google_sub))).scalar_one_or_none()
    if user is None:
        tenant = Tenant(name=email)
        db.add(tenant)
        await db.flush()
        user = User(tenant_id=tenant.id, google_sub=google_sub, email=email)
        db.add(user)
    user.email = email
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return user

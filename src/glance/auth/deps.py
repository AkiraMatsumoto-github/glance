"""ログインが要る API で使う依存関係。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from glance.auth.sessions import COOKIE_NAME, find_user
from glance.db.models import User
from glance.db.session import get_db
from glance.errors import AppError

Db = Annotated[AsyncSession, Depends(get_db)]


async def current_user(request: Request, db: Db) -> User:
    raw = request.cookies.get(COOKIE_NAME)
    user = await find_user(db, raw) if raw else None
    if user is None:
        raise AppError(401, "unauthenticated", "ログインしてください")
    return user


CurrentUser = Annotated[User, Depends(current_user)]

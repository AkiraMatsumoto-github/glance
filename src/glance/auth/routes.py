"""ログイン・ログアウト（technical_design.md §4・§6）。

Google の同意画面との行き来は、2番目の段階で OAuth クライアントができてから作る。
それまでは、フェイクモード（GLANCE_FAKE_GOOGLE=1）のときだけ、許可リストの最初の
メールアドレスとしてログインできる。
"""

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from glance.auth.deps import CurrentUser, Db
from glance.auth.sessions import (
    COOKIE_NAME,
    clear_session_cookie,
    create_session,
    delete_session,
    set_session_cookie,
    upsert_user,
)
from glance.config import Settings

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/auth/login")
async def login(request: Request, db: Db) -> Response:
    settings = _settings(request)
    if not settings.fake_google:
        log.warning("Google ログインはまだつないでいない（GLANCE_FAKE_GOOGLE=1 のときだけログインできる）")
        return RedirectResponse("/login?error=failed", status_code=303)

    emails = settings.allowed_email_list
    if not emails:
        return RedirectResponse("/login?error=not_allowed", status_code=303)
    email = emails[0]
    user = await upsert_user(db, google_sub=f"fake:{email}", email=email)
    raw = await create_session(db, user)
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(response, raw, secure=settings.secure_cookies)
    return response


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, db: Db) -> Response:
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        await delete_session(db, raw)
    response = Response(status_code=204)
    clear_session_cookie(response, secure=_settings(request).secure_cookies)
    return response


@router.get("/me")
async def me(user: CurrentUser) -> dict[str, str]:
    return {"email": user.email}

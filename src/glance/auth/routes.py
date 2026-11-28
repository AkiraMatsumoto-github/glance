"""ログイン・ログアウト（technical_design.md §4・§6）。

Google ログインは FastAPI で受ける。フェイクモード（GLANCE_FAKE_GOOGLE=1）のときは Google へ行かず、
許可リストの最初のメールアドレスとしてログインする。
"""

import asyncio
import logging
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from glance.auth import google as google_auth
from glance.auth.deps import CurrentUser, Db
from glance.auth.sessions import (
    COOKIE_NAME,
    clear_session_cookie,
    create_session,
    delete_session,
    set_session_cookie,
    upsert_user,
)
from glance.config import LOCAL_HOSTS, Settings

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)

STATE_COOKIE = "glance_oauth_state"
VERIFIER_COOKIE = "glance_oauth_verifier"
OAUTH_COOKIE_SECONDS = 600  # 同意画面から戻るまでの猶予（10分）


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _to_login(error: str) -> RedirectResponse:
    return RedirectResponse(f"/login?error={error}", status_code=303)


def _clear_oauth_cookies(response: Response, secure: bool) -> None:
    for name in (STATE_COOKIE, VERIFIER_COOKIE):
        response.delete_cookie(name, path="/api/auth", httponly=True, secure=secure, samesite="lax")


async def _sign_in(request: Request, db: Db, google_sub: str, email: str) -> RedirectResponse:
    user = await upsert_user(db, google_sub=google_sub, email=email)
    raw = await create_session(db, user)
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(response, raw, secure=_settings(request).secure_cookies)
    return response


def _is_local_request(request: Request) -> bool:
    """手元から直接来た要求か。Cloudflare を通った要求には CF-Connecting-IP が付き、ホスト名も手元のものではない。"""
    host = urlsplit(f"http://{request.headers.get('host', '')}").hostname
    return host in LOCAL_HOSTS and "cf-connecting-ip" not in request.headers


@router.get("/auth/login")
async def login(request: Request, db: Db, prompt: str | None = None) -> Response:
    settings = _settings(request)
    if settings.fake_google:
        emails = settings.allowed_email_list
        # 手元からの要求だけ（設定の確認に加えて、外から届いた要求（Cloudflare 経由・別のホスト名）を断る）
        if not emails or not _is_local_request(request):
            return _to_login("not_allowed")
        return await _sign_in(request, db, google_sub=f"fake:{emails[0]}", email=emails[0])

    start = google_auth.start_login(settings, force_consent=prompt == "consent")
    response = RedirectResponse(start.url, status_code=303)
    # 同意画面から戻ってきたときに照合する。戻りは別のサイトからの GET なので SameSite=Lax で届く
    for name, value in ((STATE_COOKIE, start.state), (VERIFIER_COOKIE, start.code_verifier)):
        response.set_cookie(
            name,
            value,
            max_age=OAUTH_COOKIE_SECONDS,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/api/auth",
        )
    return response


@router.get("/auth/callback")
async def callback(
    request: Request,
    db: Db,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    settings = _settings(request)
    response = await _callback(request, db, settings, code, state, error)
    _clear_oauth_cookies(response, settings.secure_cookies)
    return response


async def _callback(
    request: Request, db: Db, settings: Settings, code: str | None, state: str | None, error: str | None
) -> Response:
    if error:
        # 同意画面で「キャンセル」を押すと access_denied で戻ってくる
        return _to_login("cancelled" if error == "access_denied" else "failed")
    saved_state = request.cookies.get(STATE_COOKIE)
    verifier = request.cookies.get(VERIFIER_COOKIE)
    if not code or not state or not saved_state or not verifier or state != saved_state:
        log.warning("Google から戻ったときの state が合わない、または期限切れ")
        return _to_login("failed")

    try:
        tokens = await asyncio.to_thread(google_auth.exchange_code, settings, state, verifier, code)
        claims = await asyncio.to_thread(google_auth.verify_id_token, settings, tokens.id_token)
    except Exception:
        log.exception("Google のトークンを取れなかった")
        return _to_login("failed")

    email = str(claims.get("email", "")).lower()
    if not claims.get("email_verified") or email not in settings.allowed_email_list:
        # 許可していないアカウント。トークンは保存しない
        return _to_login("not_allowed")

    user = await upsert_user(db, google_sub=str(claims["sub"]), email=email)
    if tokens.refresh_token:
        user.refresh_token_encrypted = request.app.state.cipher.encrypt(tokens.refresh_token)
        user.scopes = " ".join(tokens.scopes)
        await db.commit()
    elif not user.refresh_token_encrypted:
        # 更新トークンがもらえず、保存したものもない。同意画面を出してもらい直す
        return RedirectResponse("/api/auth/login?prompt=consent", status_code=303)

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

"""Google ログインの流れ（Google との通信は差し替える）。"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from glance.auth import google as google_auth
from glance.auth.crypto import TokenCipher
from glance.auth.routes import STATE_COOKIE, VERIFIER_COOKIE
from glance.main import create_app
from tests.conftest import EMAIL, TOKEN_KEY, _clean, make_settings


@pytest.fixture
async def google_app(database_url: str) -> AsyncIterator[FastAPI]:
    _clean(database_url)
    app = create_app(make_settings(database_url, fake_google=False))
    yield app
    await app.state.engine.dispose()


@pytest.fixture
async def gclient(google_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=google_app), base_url="http://localhost") as c:
        yield c


def fake_google(monkeypatch: pytest.MonkeyPatch, *, refresh_token: str | None = "refresh-1", email: str = EMAIL,
                verified: bool = True) -> None:
    def exchange(settings, state, verifier, code):  # type: ignore[no-untyped-def]
        assert code == "good-code" and verifier
        return google_auth.Tokens(refresh_token=refresh_token, id_token="id-token", scopes=google_auth.SCOPES)

    def verify(settings, token):  # type: ignore[no-untyped-def]
        return {"sub": "google-sub-1", "email": email.upper(), "email_verified": verified}

    monkeypatch.setattr(google_auth, "exchange_code", exchange)
    monkeypatch.setattr(google_auth, "verify_id_token", verify)


async def start(client: AsyncClient, query: str = "") -> dict[str, list[str]]:
    response = await client.get(f"/api/auth/login{query}")
    assert response.status_code == 303
    url = urlparse(response.headers["location"])
    assert url.netloc == "accounts.google.com"
    return parse_qs(url.query)


def db_url(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


async def test_login_redirects_to_google_with_pkce(gclient: AsyncClient) -> None:
    params = await start(gclient)
    assert params["access_type"] == ["offline"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost:3100/api/auth/callback"]
    assert "https://www.googleapis.com/auth/analytics.readonly" in params["scope"][0]
    assert "prompt" not in params
    assert gclient.cookies.get(STATE_COOKIE) == params["state"][0]
    assert gclient.cookies.get(VERIFIER_COOKIE)
    assert (await start(gclient, "?prompt=consent"))["prompt"] == ["consent"]


async def test_callback_signs_in_and_stores_encrypted_token(
    gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    fake_google(monkeypatch)
    state = (await start(gclient))["state"][0]
    response = await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert (await gclient.get("/api/me")).json() == {"email": EMAIL}
    with psycopg.connect(db_url(database_url)) as conn:
        sub, stored, scopes = conn.execute("SELECT google_sub, refresh_token_encrypted, scopes FROM users").fetchone()
    assert sub == "google-sub-1"
    assert stored != "refresh-1"  # 暗号化して入れている
    assert TokenCipher(TOKEN_KEY).decrypt(stored) == "refresh-1"
    assert "analytics.readonly" in scopes
    # state と code_verifier のクッキーは使い終わったら消す
    assert gclient.cookies.get(STATE_COOKIE) is None


async def test_state_mismatch_is_rejected(gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_google(monkeypatch)
    await start(gclient)
    response = await gclient.get("/api/auth/callback?code=good-code&state=other")
    assert response.headers["location"] == "/login?error=failed"
    assert (await gclient.get("/api/me")).status_code == 401


async def test_cancel_on_consent_screen(gclient: AsyncClient) -> None:
    await start(gclient)
    response = await gclient.get("/api/auth/callback?error=access_denied")
    assert response.headers["location"] == "/login?error=cancelled"


async def test_unlisted_email_is_rejected_without_storing(
    gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    fake_google(monkeypatch, email="someone@example.com")
    state = (await start(gclient))["state"][0]
    response = await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    assert response.headers["location"] == "/login?error=not_allowed"
    with psycopg.connect(db_url(database_url)) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone() == (0,)


async def test_unverified_email_is_rejected(gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_google(monkeypatch, verified=False)
    state = (await start(gclient))["state"][0]
    response = await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    assert response.headers["location"] == "/login?error=not_allowed"


async def test_no_refresh_token_asks_for_consent(gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_google(monkeypatch, refresh_token=None)
    state = (await start(gclient))["state"][0]
    response = await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    assert response.headers["location"] == "/api/auth/login?prompt=consent"
    assert (await gclient.get("/api/me")).status_code == 401


async def test_second_login_keeps_saved_token(
    gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    fake_google(monkeypatch)
    state = (await start(gclient))["state"][0]
    await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    # 2回目は Google が更新トークンを返さない。保存済みのものを使い続ける
    fake_google(monkeypatch, refresh_token=None)
    state = (await start(gclient))["state"][0]
    response = await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    assert response.headers["location"] == "/"
    with psycopg.connect(db_url(database_url)) as conn:
        stored = conn.execute("SELECT refresh_token_encrypted FROM users").fetchone()[0]
    assert TokenCipher(TOKEN_KEY).decrypt(stored) == "refresh-1"


async def test_user_without_token_must_reauth(
    gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    fake_google(monkeypatch)
    state = (await start(gclient))["state"][0]
    await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    with psycopg.connect(db_url(database_url), autocommit=True) as conn:
        conn.execute("UPDATE users SET refresh_token_encrypted = NULL")
    response = await gclient.get("/api/realtime")
    assert response.status_code == 401
    assert response.json()["code"] == "reauth_required"

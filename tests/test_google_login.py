"""Google ログインの流れ（Google との通信は差し替える）。"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from glance.auth import google as google_auth
from glance.auth.crypto import TokenCipher
from glance.auth.cookies import OAUTH_STATE, OAUTH_VERIFIER
from glance.main import create_app
from tests.conftest import EMAIL, TOKEN_KEY, clean_database, db_query, make_settings


@pytest.fixture
async def google_app(database_url: str) -> AsyncIterator[FastAPI]:
    clean_database(database_url)
    app = create_app(make_settings(database_url, fake_google=False))
    yield app
    await app.state.engine.dispose()


@pytest.fixture
async def gclient(google_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=google_app), base_url="http://localhost") as c:
        yield c


def fake_google(monkeypatch: pytest.MonkeyPatch, *, refresh_token: str | None = "refresh-1", email: str = EMAIL,
                verified: bool = True, sub: str = "google-sub-1") -> None:
    def exchange(settings, state, verifier, code):  # type: ignore[no-untyped-def]
        assert code == "good-code" and verifier
        return google_auth.Tokens(refresh_token=refresh_token, id_token="id-token", scopes=google_auth.SCOPES)

    def verify(settings, token):  # type: ignore[no-untyped-def]
        return {"sub": sub, "email": email.upper(), "email_verified": verified}

    monkeypatch.setattr(google_auth, "exchange_code", exchange)
    monkeypatch.setattr(google_auth, "verify_id_token", verify)


async def start(client: AsyncClient, query: str = "") -> dict[str, list[str]]:
    response = await client.get(f"/api/auth/login{query}")
    assert response.status_code == 303
    url = urlparse(response.headers["location"])
    assert url.netloc == "accounts.google.com"
    return parse_qs(url.query)


async def test_login_redirects_to_google_with_pkce(gclient: AsyncClient) -> None:
    params = await start(gclient)
    assert params["access_type"] == ["offline"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost:3100/api/auth/callback"]
    assert "https://www.googleapis.com/auth/analytics.readonly" in params["scope"][0]
    assert "prompt" not in params
    assert gclient.cookies.get(OAUTH_STATE) == params["state"][0]
    assert gclient.cookies.get(OAUTH_VERIFIER)
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
    [(sub, stored, scopes)] = db_query(database_url, "SELECT google_sub, refresh_token_encrypted, scopes FROM users")
    assert sub == "google-sub-1"
    assert stored != "refresh-1"  # 暗号化して入れている
    assert TokenCipher(TOKEN_KEY).decrypt(stored) == "refresh-1"
    assert "analytics.readonly" in scopes
    # state と code_verifier のクッキーは使い終わったら消す
    assert gclient.cookies.get(OAUTH_STATE) is None


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
    assert db_query(database_url, "SELECT count(*) FROM users") == [(0,)]


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
    [(stored,)] = db_query(database_url, "SELECT refresh_token_encrypted FROM users")
    assert TokenCipher(TOKEN_KEY).decrypt(stored) == "refresh-1"


async def test_user_without_token_must_reauth(
    gclient: AsyncClient, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    fake_google(monkeypatch)
    state = (await start(gclient))["state"][0]
    await gclient.get(f"/api/auth/callback?code=good-code&state={state}")
    db_query(database_url, "UPDATE users SET refresh_token_encrypted = NULL")
    response = await gclient.get("/api/realtime")
    assert response.status_code == 401
    assert response.json()["code"] == "reauth_required"


def test_id_token_allows_small_clock_skew(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    # サーバーの時計が Google より少し遅れていても、ID トークンを断らない（2026-11-28 手元で1秒の遅れで失敗した）
    seen: dict[str, object] = {}

    def verify(token, request, audience, clock_skew_in_seconds=0):  # type: ignore[no-untyped-def]
        seen["skew"] = clock_skew_in_seconds
        return {"sub": "s"}

    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", verify)
    google_auth.verify_id_token(make_settings(database_url, fake_google=False), "id-token")
    assert seen["skew"] == google_auth.CLOCK_SKEW_SECONDS >= 5


async def test_cookies_use_host_prefix_on_https(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    # 本番（https）では、クッキーに __Host- を付ける（Secure・Path=/・Domain なし。ほかのサブドメインから差し込めない）
    clean_database(database_url)
    app = create_app(make_settings(database_url, fake_google=False, public_url="https://glance.example.com"))
    fake_google(monkeypatch)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://glance.example.com") as client:
            response = await client.get("/api/auth/login")
            cookies = response.headers.get_list("set-cookie")
            assert sorted(c.split("=")[0] for c in cookies) == [f"__Host-{OAUTH_STATE}", f"__Host-{OAUTH_VERIFIER}"]
            assert all("Secure" in c and "Path=/;" in c and "Domain" not in c for c in cookies)
            state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]

            response = await client.get("/api/auth/callback", params={"code": "good-code", "state": state})
            session = [c for c in response.headers.get_list("set-cookie") if c.startswith("__Host-glance_session=")]
            assert len(session) == 1 and "Secure" in session[0] and "Path=/;" in session[0]
            # __Host- の付いたセッションで入れる。付いていない名前のクッキー（差し込まれたもの）は使わない
            assert (await client.get("/api/me")).status_code == 200
            raw = client.cookies.get("__Host-glance_session")
            client.cookies.clear()
            client.cookies.set("glance_session", raw or "")
            assert (await client.get("/api/me")).status_code == 401
    finally:
        await app.state.engine.dispose()


async def test_each_account_has_its_own_data(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    # 初めてログインした人には、その人だけの顧客を作る。ほかの人のサイト・キーは見えない（2026-11-28 利用者の決定）
    clean_database(database_url)
    other = "other@example.com"
    app = create_app(make_settings(database_url, fake_google=False, allowed_emails=f"{EMAIL},{other}"))

    async def sign_in(sub: str, email: str) -> AsyncClient:
        fake_google(monkeypatch, sub=sub, email=email)
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost")
        state = (await start(client))["state"][0]
        assert (await client.get(f"/api/auth/callback?code=good-code&state={state}")).headers["location"] == "/"
        return client

    a = await sign_in("google-sub-1", EMAIL)
    b = await sign_in("google-sub-2", other)
    try:
        users = dict(db_query(database_url, "SELECT email, tenant_id FROM users"))
        assert users[EMAIL] != users[other] and 1 not in users.values()  # どちらも、マイグレーションの「自社」には入らない
        [(site_id,)] = db_query(
            database_url,
            "INSERT INTO sites (tenant_id, name, sort_order, timezone, ga4_property_id)"
            " VALUES (%s, 'A のサイト', 0, 'Asia/Tokyo', '900000001') RETURNING id",
            (users[EMAIL],),
        )
        db_query(
            database_url,
            "INSERT INTO bing_keys (tenant_id, name, key_encrypted, last4) VALUES (%s, 'A のキー', 'x', 'aaaa')",
            (users[EMAIL],),
        )
        assert [s["name"] for s in (await a.get("/api/sites")).json()] == ["A のサイト"]
        assert [k["name"] for k in (await a.get("/api/bing/keys")).json()] == ["A のキー"]
        assert (await b.get("/api/sites")).json() == []
        assert (await b.get("/api/bing/keys")).json() == []
        assert (await b.get(f"/api/sites/{site_id}/gsc")).status_code == 404
        # ログインし直しても、同じ顧客のまま（顧客は増えない）
        again = await sign_in("google-sub-1", EMAIL)
        assert [s["name"] for s in (await again.get("/api/sites")).json()] == ["A のサイト"]
        await again.aclose()
        assert db_query(database_url, "SELECT count(*) FROM tenants") == [(3,)]
    finally:
        await a.aclose()
        await b.aclose()
        await app.state.engine.dispose()

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from glance.auth.cookies import SESSION
from glance.main import create_app
from tests.conftest import EMAIL, JSON, db_query, make_settings



async def test_me_requires_login(client: AsyncClient) -> None:
    response = await client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_fake_login_me_logout(client: AsyncClient) -> None:
    response = await client.get("/api/auth/login")
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION}=")  # 手元（http）では __Host- を付けない
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie  # 手元（http）では Secure を付けない

    response = await client.get("/api/me")
    assert response.status_code == 200
    assert response.json() == {"email": EMAIL}
    assert response.headers["cache-control"] == "no-store"

    response = await client.post("/api/auth/logout", content="{}", headers=JSON)
    assert response.status_code == 204
    assert (await client.get("/api/me")).status_code == 401


async def test_login_rejected_without_allowed_email(database_url: str) -> None:
    app = create_app(make_settings(database_url, allowed_emails=""))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as c:
        response = await c.get("/api/auth/login")
    await app.state.engine.dispose()
    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=not_allowed"


async def test_expired_session_is_rejected(logged_in: AsyncClient, database_url: str) -> None:
    db_query(database_url, "UPDATE sessions SET expires_at = %s", (datetime.now(UTC) - timedelta(minutes=1),))
    assert (await logged_in.get("/api/me")).status_code == 401
    assert db_query(database_url, "SELECT count(*) FROM sessions") == [(0,)]


async def test_write_requires_json(logged_in: AsyncClient) -> None:
    response = await logged_in.post("/api/auth/logout", data={"a": "b"})
    assert response.status_code == 415
    assert (await logged_in.get("/api/me")).status_code == 200


def test_fake_mode_refuses_public_url(database_url: str) -> None:
    with pytest.raises(ValueError):
        create_app(make_settings(database_url, public_url="https://glance.example.com"))


def test_google_mode_requires_settings(database_url: str) -> None:
    with pytest.raises(ValueError, match="GLANCE_TOKEN_KEY"):
        create_app(make_settings(database_url, fake_google=False, token_key=""))


async def test_unknown_api_path_is_json_404(client: AsyncClient) -> None:
    response = await client.get("/api/nothing")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_static_pages(database_url: str, tmp_path: object, app: FastAPI) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    (root / "index.html").write_text("top")
    (root / "login.html").write_text("login")
    (root / "settings").mkdir()
    (root / "settings" / "sites.html").write_text("sites")
    (root / "404.html").write_text("missing")
    web = create_app(make_settings(database_url, static_dir=str(root)))
    async with AsyncClient(transport=ASGITransport(app=web), base_url="http://localhost") as c:
        assert (await c.get("/")).text == "top"
        assert (await c.get("/login")).text == "login"
        assert (await c.get("/settings/sites")).text == "sites"
        missing = await c.get("/nothing")
        assert missing.status_code == 404
        assert missing.text == "missing"
        assert (await c.get("/api/me")).status_code == 401
        # 画面・API・断った応答のどれにも、フレームに埋め込ませない・種類を推測させないヘッダーを付ける
        responses = [
            await c.get("/"),
            missing,
            await c.get("/api/me"),
            await c.post("/api/sites", content="x", headers={"content-type": "text/plain"}),
        ]
        assert [r.status_code for r in responses] == [200, 404, 401, 415]
        for r in responses:
            assert r.headers["x-frame-options"] == "DENY"
            assert r.headers["content-security-policy"] == "frame-ancestors 'none'"
            assert r.headers["x-content-type-options"] == "nosniff"
    await web.state.engine.dispose()


async def test_large_body_is_rejected_before_login(client: AsyncClient) -> None:
    # 本文はログインの確認より先に読まれるので、大きな本文は読まずに断る
    response = await client.post("/api/sites", content=b"{" + b" " * 70_000 + b"}", headers=JSON)
    assert response.status_code == 413


async def test_user_removed_from_allowlist_is_signed_out(logged_in: AsyncClient, database_url: str) -> None:
    # 許可リストにいない人になったら（ここではメールアドレスを変えて試す）、セッションが残っていても入れない
    db_query(database_url, "UPDATE users SET email = 'removed@example.com'")
    response = await logged_in.get("/api/sites")
    assert (response.status_code, response.json()["code"]) == (401, "not_allowed")
    # 全部の端末からログアウトさせる
    assert db_query(database_url, "SELECT count(*) FROM sessions") == [(0,)]


@pytest.mark.parametrize(
    "public_url",
    ["", "https://glance.example.com", "http://localhost.example.com", "http://127.0.0.1.nip.io:3100"],
)
def test_fake_mode_only_on_local_url(database_url: str, public_url: str) -> None:
    with pytest.raises(ValueError, match="手元でだけ使える"):
        create_app(make_settings(database_url, public_url=public_url))


@pytest.mark.parametrize(
    "headers",
    [{"host": "glance.example.com"}, {"cf-connecting-ip": "203.0.113.5"}],
)
async def test_fake_login_refuses_requests_from_outside(client: AsyncClient, headers: dict[str, str]) -> None:
    # 設定の確認に加えて、Cloudflare を通った要求・手元でないホスト名の要求は、フェイクのログインを断る
    response = await client.get("/api/auth/login", headers=headers)
    assert response.headers["location"] == "/login?error=not_allowed"
    assert (await client.get("/api/me")).status_code == 401

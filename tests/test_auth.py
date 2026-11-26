from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from glance.auth.sessions import COOKIE_NAME
from glance.main import create_app
from tests.conftest import EMAIL, make_settings

JSON = {"content-type": "application/json"}


async def test_me_requires_login(client: AsyncClient) -> None:
    response = await client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


async def test_fake_login_me_logout(client: AsyncClient) -> None:
    response = await client.get("/api/auth/login")
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert f"{COOKIE_NAME}=" in cookie
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


async def test_login_without_fake_mode_is_not_available_yet(database_url: str) -> None:
    app = create_app(make_settings(database_url, fake_google=False))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as c:
        response = await c.get("/api/auth/login")
    await app.state.engine.dispose()
    assert response.headers["location"] == "/login?error=failed"


async def test_expired_session_is_rejected(logged_in: AsyncClient, database_url: str) -> None:
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("UPDATE sessions SET expires_at = %s", (datetime.now(UTC) - timedelta(minutes=1),))
    assert (await logged_in.get("/api/me")).status_code == 401
    with psycopg.connect(url, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone() == (0,)


async def test_write_requires_json(logged_in: AsyncClient) -> None:
    response = await logged_in.post("/api/auth/logout", data={"a": "b"})
    assert response.status_code == 415
    assert (await logged_in.get("/api/me")).status_code == 200


def test_fake_mode_refuses_public_url(database_url: str) -> None:
    with pytest.raises(ValueError):
        create_app(make_settings(database_url, public_url="https://glance.example.com"))


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
    await web.state.engine.dispose()

"""テストの共通部品。手元の DB コンテナに glance_test を作り、マイグレーションを当てて使う。"""

from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from cryptography.fernet import Fernet
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from glance.bing.client import BingClient, FakeBingClient
from glance.config import Settings
from glance.google.fake import FakeGoogleClient
from glance.google.client import GoogleClient
from glance.main import create_app

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "glance_test"
EMAIL = "tester@example.com"
TOKEN_KEY = Fernet.generate_key().decode()


@pytest.fixture(scope="session")
def database_url() -> str:
    base = make_url(Settings().database_url)  # type: ignore[call-arg]
    test_url = base.set(database=TEST_DB)
    admin = base.set(drivername="postgresql", database="postgres")
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    url = test_url.render_as_string(hide_password=False)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    return url


def _clean(database_url: str) -> None:
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("TRUNCATE sessions, connections, sites, bing_keys, users RESTART IDENTITY CASCADE")
        conn.execute("DELETE FROM tenants WHERE id <> 1")


def make_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": database_url,
        "allowed_emails": EMAIL,
        "public_url": "http://localhost:3100",
        "fake_google": True,
        "static_dir": "/nonexistent",
        "google_client_id": "test-client.apps.googleusercontent.com",
        "google_client_secret": "test-secret",
        "token_key": TOKEN_KEY,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def google() -> GoogleClient:
    """テストで差し替える GA4 クライアント。既定は待ち時間のないフェイク。"""
    return FakeGoogleClient(latency=(0, 0), clock=lambda: 1_800_000_000.0)


@pytest.fixture
def bing() -> BingClient:
    """テストで差し替える Bing クライアント。既定は「bad」で始まるキーだけを使えないキーとするダミー。"""
    return FakeBingClient()


@pytest.fixture
async def app(database_url: str, google: GoogleClient, bing: BingClient) -> AsyncIterator[FastAPI]:
    _clean(database_url)
    application = create_app(
        make_settings(database_url), google_factory=lambda _user: google, realtime_timeout=0.5, bing_client=bing
    )
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


@pytest.fixture
async def logged_in(client: AsyncClient) -> AsyncClient:
    response = await client.get("/api/auth/login")
    assert response.status_code == 303
    return client

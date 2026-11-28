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
    base = make_url(Settings().database_url.get_secret_value())  # type: ignore[call-arg]
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


JSON = {"content-type": "application/json"}  # 本文の無い書き込み（DELETE など）に付ける


def db_query(database_url: str, sql: str, params: tuple = ()) -> list[tuple]:
    """テスト用の DB で SQL を1つ動かす（すぐ確定する）。結果の行を返す（行を返さない文は空）。"""
    url = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True) as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall() if cursor.description else []


def clean_database(database_url: str) -> None:
    """テストの前に、テスト用の DB を空にする（顧客は、マイグレーションで作る1つだけにする）。"""
    db_query(database_url, "TRUNCATE sessions, connections, sites, bing_keys, users RESTART IDENTITY CASCADE")
    db_query(database_url, "DELETE FROM tenants WHERE id <> 1")


def other_tenant(database_url: str) -> int:
    """別の顧客を作り、その ID を返す（新しい人の顧客と ID がぶつからないよう、ID は DB に振らせる）。"""
    [(tenant_id,)] = db_query(database_url, "INSERT INTO tenants (name) VALUES ('別の顧客') RETURNING id")
    return tenant_id


async def add_site(client: AsyncClient, property_id: str, gsc_site_url: str | None = None) -> dict:
    """GA4 のプロパティをサイトとして追加する（Search Console も一緒に紐づけるときは gsc_site_url）。"""
    body: dict[str, str] = {"property_id": property_id}
    if gsc_site_url is not None:
        body["gsc_site_url"] = gsc_site_url
    response = await client.post("/api/sites", json=body)
    assert response.status_code == 201, response.text
    return response.json()


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
    """テストで差し替える Google（GA4・Search Console）のクライアント。既定は待ち時間のないフェイク。"""
    return FakeGoogleClient(latency=(0, 0), clock=lambda: 1_800_000_000.0)


@pytest.fixture
def bing() -> BingClient:
    """テストで差し替える Bing クライアント。既定は「bad」で始まるキーだけを使えないキーとするダミー。"""
    return FakeBingClient()


@pytest.fixture
async def app(database_url: str, google: GoogleClient, bing: BingClient) -> AsyncIterator[FastAPI]:
    clean_database(database_url)
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

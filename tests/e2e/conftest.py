"""画面の自動テスト（ブラウザで動かす）の共通部品。

フェイクモード（Google・Bing はダミー）の API と、書き出した画面（web/out）を、テストの中で起動して使う。
ブラウザが要るので、GLANCE_E2E=1 のときだけ動かす（README の「テスト」）。

    cd web && npm run build && cd ..
    GLANCE_E2E=1 uv run pytest tests/e2e

ブラウザは Playwright のもの（uv run playwright install chromium）。別の場所のものを使うときは
GLANCE_E2E_CHROMIUM に実行ファイルのパスを入れる。
"""

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

from glance.main import create_app
from tests.conftest import _clean, make_settings

ROOT = Path(__file__).resolve().parents[2]
WEB_OUT = ROOT / "web" / "out"

HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # ブラウザが要るので、GLANCE_E2E=1 のときだけ動かす（ふだんの uv run pytest では飛ばす）
    if os.environ.get("GLANCE_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="画面のテストは GLANCE_E2E=1 のときだけ動かす")
    for item in items:
        if HERE in item.path.parents:
            item.add_marker(skip)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def base_url(database_url: str) -> Iterator[str]:
    """API と画面を、テスト用の DB・フェイクモードで起動する。"""
    if not (WEB_OUT / "index.html").exists():
        pytest.skip("web/out がありません。先に cd web && npm run build")
    _clean(database_url)
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    app = create_app(make_settings(database_url, static_dir=str(WEB_OUT), public_url=url))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield url
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        executable = os.environ.get("GLANCE_E2E_CHROMIUM") or None
        browser = p.chromium.launch(executable_path=executable)
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ja-JP")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    yield page
    context.close()
    assert errors == [], f"画面のエラー: {errors}"

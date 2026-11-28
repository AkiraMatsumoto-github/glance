"""画面の主な流れを、ブラウザで確かめる（GLANCE_E2E=1 のときだけ。tests/e2e/conftest.py）。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from playwright.sync_api import Page, expect

from glance.bing.client import FakeBingClient
from glance.db.session import create_engine, create_sessionmaker
from glance.google.fake import FakeGoogleClient
from glance.sync.runner import Syncer
from glance.sync.sitemap import FakeSitemapFetcher
from tests.conftest import EMAIL


def _idle(page: Page) -> None:
    """取得中の印が消えるまで待つ。"""
    expect(page.get_by_text("取得中…")).to_have_count(0, timeout=20_000)


def test_demo_screens(page: Page, base_url: str) -> None:
    # ログインせずに見られる。数字はダミー
    page.goto(f"{base_url}/login")
    page.get_by_role("link", name="ログインせずにデモを見る").click()
    expect(page.get_by_text("デモサイト A").first).to_be_visible(timeout=20_000)
    _idle(page)

    page.get_by_role("navigation").get_by_role("link", name="SEO").click()
    expect(page.get_by_role("heading", name="日ごとの推移")).to_be_visible(timeout=20_000)
    _idle(page)
    headings = page.get_by_role("heading", level=2).all_inner_texts()
    assert headings[:2] == ["日ごとの推移", "インデックス"]
    page.get_by_role("button", name="Bing").click()
    _idle(page)
    expect(page.get_by_role("group", name="指標").last).to_contain_text("クロールエラー")

    # サイト設定は見るだけ
    page.get_by_role("navigation").get_by_role("link", name="サイト設定").click()
    expect(page.get_by_label("デモサイト Aの名前")).to_be_visible(timeout=20_000)
    assert page.get_by_role("button", name="削除").first.is_disabled()


def test_link_import_and_seo(page: Page, base_url: str, database_url: str) -> None:
    # ログイン（フェイク）→ サイトを追加（同じドメインの Search Console も一緒に）
    page.goto(f"{base_url}/login")
    page.get_by_text("Google でログイン").click()
    page.wait_for_url(f"{base_url}/")
    page.get_by_role("navigation").get_by_role("link", name="サイト設定").click()
    page.get_by_role("button", name="サイトを追加").click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("LogiShift", exact=True)).to_be_visible(timeout=20_000)
    expect(dialog.get_by_label("LogiShiftと一緒に紐づける Search Console のサイト")).to_have_value("sc-domain:logishift.example")
    dialog.locator("li").filter(has=page.get_by_text("LogiShift", exact=True)).get_by_role("button", name="追加").click()
    expect(dialog).to_be_hidden(timeout=20_000)

    # Bing: キーを入れて、サイトを選ぶ
    row = page.get_by_role("row").filter(has=page.get_by_label("LogiShiftの名前"))
    row.get_by_role("cell").nth(4).get_by_role("button", name="設定する").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("キーの名前").fill("テスト")
    dialog.get_by_label("API キー").fill("good-key-1111")
    dialog.get_by_role("button", name="キーを保存").click()
    expect(dialog.get_by_text("末尾 1111")).to_be_visible(timeout=20_000)
    dialog.get_by_label("https://www.logishift.example/").check()
    dialog.get_by_role("button", name="保存", exact=True).click()
    expect(dialog).to_be_hidden(timeout=20_000)
    expect(row.get_by_text("連携あり")).to_have_count(2)

    # 取り込む（コマンドと同じ処理）。ダミーの Google・Bing・サイトマップ
    async def sync() -> None:
        engine = create_engine(database_url)
        try:
            syncer = Syncer(
                create_sessionmaker(engine),
                lambda _user: FakeGoogleClient(latency=(0, 0)),
                FakeBingClient(),
                None,
                date.today(),
                sitemap_fetcher=FakeSitemapFetcher(),
                allowed_emails=[EMAIL],
            )
            outcomes = await syncer.run({"gsc"})
            assert all(o.error is None for o in outcomes), outcomes
        finally:
            await engine.dispose()

    # ブラウザ（Playwright）が動かしている処理の流れとは別のスレッドで動かす
    with ThreadPoolExecutor(1) as pool:
        pool.submit(asyncio.run, sync()).result()

    # SEO: 連携したサイトの数字と、インデックスの表
    page.get_by_role("navigation").get_by_role("link", name="SEO").click()
    expect(page.get_by_text("までのデータ").first).to_be_visible(timeout=20_000)
    _idle(page)
    expect(page.get_by_role("checkbox", name="LogiShift")).to_be_visible()
    index = page.locator("section").filter(has=page.get_by_role("heading", name="インデックス", exact=True))
    expect(index.get_by_role("row").nth(1)).to_contain_text("LogiShift")

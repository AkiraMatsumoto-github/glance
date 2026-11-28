"""Search Console・Bing の数字を取り込むコマンド（technical_design.md §6.5）。

    uv run python -m glance.sync              # 紐づけた全サイトの GSC と Bing
    uv run python -m glance.sync --source bing
    uv run python -m glance.sync --site 1 --site 3

接続先と鍵は .env（GLANCE_DATABASE_URL・GLANCE_TOKEN_KEY など）から読む。VPS に出すまでは手元で動かす。
"""

import argparse
import asyncio
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from glance.auth.crypto import TokenCipher
from glance.bing.client import FakeBingClient, RealBingClient
from glance.config import Settings
from glance.db.session import create_engine, create_sessionmaker
from glance.google.factory import default_google_factory
from glance.logs import quiet_secret_logs
from glance.sync.common import Outcome
from glance.sync.runner import Syncer
from glance.sync.sitemap import FakeSitemapFetcher, HttpSitemapFetcher

JST = ZoneInfo("Asia/Tokyo")


def _print(outcome: Outcome) -> None:
    span = f"{outcome.start}〜{outcome.end}" if outcome.start else "-"
    status = "OK" if outcome.error is None else f"失敗: {outcome.error}"
    print(f"{outcome.site}\t{outcome.table}\t{span}\t{outcome.rows}行\t{status}", flush=True)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m glance.sync", description="Search Console・Bing の数字を取り込む")
    parser.add_argument("--source", choices=["gsc", "bing", "all"], default="all", help="取るソース（既定は両方）")
    parser.add_argument("--site", type=int, action="append", help="サイト ID（何度でも。省略すると紐づけた全サイト）")
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]
    settings.check()  # API と同じく、起動してはいけない組み合わせ（本番でのフェイクモードなど）を止める
    quiet_secret_logs()
    engine = create_engine(settings.database_url.get_secret_value())
    token_key = settings.token_key.get_secret_value()
    cipher = TokenCipher(token_key) if token_key else None
    syncer = Syncer(
        create_sessionmaker(engine),
        default_google_factory(settings, cipher),
        FakeBingClient() if settings.fake_google else RealBingClient(),
        cipher,
        today=datetime.now(JST).date(),
        sitemap_fetcher=FakeSitemapFetcher() if settings.fake_google else HttpSitemapFetcher(),
        allowed_emails=settings.allowed_email_list,
        report=_print,
    )
    sources = {"gsc", "bing"} if args.source == "all" else {args.source}
    try:
        outcomes = await syncer.run(sources, args.site)
    finally:
        await engine.dispose()
    if not outcomes:
        print("取り込むサイトがありません。サイト設定で Search Console・Bing を紐づけてください。")
    return 1 if any(o.error for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

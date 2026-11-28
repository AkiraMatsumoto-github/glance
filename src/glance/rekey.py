"""暗号化の鍵を入れ替えた後に、保存した秘密の値を新しい鍵で暗号化し直すコマンド（technical_design.md §5）。

    uv run python -m glance.rekey --check   # 古い鍵のままの値を数えるだけ（書き換えない）
    uv run python -m glance.rekey           # GLANCE_TOKEN_KEY の先頭の（新しい）鍵で暗号化し直す

対象は、利用者の更新トークン（users.refresh_token_encrypted）と Bing のキー（bing_keys.key_encrypted）。
どの鍵でも復号できない値が1つでもあれば、何も書き換えずに止める（古い鍵を並べ忘れたときに、値を壊さないため）。
値そのものは表示しない（件数と、復号できなかった行の ID だけ）。
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field

from cryptography.fernet import InvalidToken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glance.auth.crypto import TokenCipher
from glance.config import Settings
from glance.db.models import BingKey, User
from glance.db.session import create_engine, create_sessionmaker
from glance.logs import quiet_secret_logs

TARGETS = [(User, "refresh_token_encrypted"), (BingKey, "key_encrypted")]


@dataclass
class RekeyResult:
    target: str  # 表.列
    total: int
    old: int  # 古い鍵で暗号化されていた値の数（--check でなければ、暗号化し直した数）
    broken: list[int] = field(default_factory=list)  # どの鍵でも復号できなかった行の ID


async def rekey(sessionmaker: async_sessionmaker[AsyncSession], cipher: TokenCipher, *, write: bool) -> list[RekeyResult]:
    results: list[RekeyResult] = []
    async with sessionmaker() as db:
        updates: list[tuple[type[User] | type[BingKey], str, int, str]] = []
        for model, column in TARGETS:
            value_column = getattr(model, column)
            # 取り込み・ログインが同じ行を同時に書き換えないよう、終わるまで行を押さえる
            rows = (await db.execute(select(model.id, value_column).where(value_column.is_not(None)).with_for_update())).all()
            result = RekeyResult(f"{model.__tablename__}.{column}", len(rows), 0)
            for row_id, value in rows:
                if cipher.is_current(value):
                    continue
                try:
                    updates.append((model, column, row_id, cipher.rotate(value)))
                    result.old += 1
                except InvalidToken:
                    result.broken.append(row_id)
            results.append(result)
        if write and updates and not any(r.broken for r in results):
            for model, column, row_id, value in updates:
                await db.execute(update(model).where(model.id == row_id).values({column: value}))
            await db.commit()
    return results


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m glance.rekey", description="秘密の値を新しい鍵で暗号化し直す")
    parser.add_argument("--check", action="store_true", help="古い鍵のままの値を数えるだけ（書き換えない）")
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]
    settings.check()
    quiet_secret_logs()
    token_key = settings.token_key.get_secret_value()
    if not token_key:
        print("GLANCE_TOKEN_KEY が空です。")
        return 1
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        results = await rekey(create_sessionmaker(engine), TokenCipher(token_key), write=not args.check)
    finally:
        await engine.dispose()

    broken = any(r.broken for r in results)
    for r in results:
        done = "古い鍵のまま" if args.check or broken else "暗号化し直した"
        line = f"{r.target}\t全{r.total}件\t{done} {r.old}件"
        if r.broken:
            line += f"\tどの鍵でも復号できない {len(r.broken)}件（id: {', '.join(map(str, r.broken))}）"
        print(line)
    if broken:
        print("復号できない値があるので、何も書き換えていません。GLANCE_TOKEN_KEY に古い鍵を並べたか確かめてください。")
        return 1
    if not args.check:
        print("終わりました。--check で 0件になったら、GLANCE_TOKEN_KEY から古い鍵を外せます。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

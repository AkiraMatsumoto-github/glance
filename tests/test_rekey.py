"""鍵を入れ替えた後の、暗号化し直し（python -m glance.rekey）。"""

from cryptography.fernet import Fernet
from fastapi import FastAPI

from glance.auth.crypto import TokenCipher
from glance.rekey import rekey
from tests.conftest import TOKEN_KEY, db_query

OLD = TokenCipher(TOKEN_KEY)
NEW_KEY = Fernet.generate_key().decode()


def _stored(database_url: str) -> list[str]:
    users = db_query(database_url, "SELECT refresh_token_encrypted FROM users WHERE refresh_token_encrypted IS NOT NULL ORDER BY id")
    keys = db_query(database_url, "SELECT key_encrypted FROM bing_keys ORDER BY id")
    return [value for (value,) in users + keys]


async def test_rekey_moves_values_to_the_new_key(app: FastAPI, database_url: str) -> None:
    db_query(
        database_url,
        "INSERT INTO users (tenant_id, google_sub, email, refresh_token_encrypted) VALUES (1, 's1', 'a@example.com', %s)",
        (OLD.encrypt("refresh-1"),),
    )
    db_query(
        database_url,
        "INSERT INTO bing_keys (tenant_id, name, key_encrypted, last4) VALUES (1, 'k', %s, '1234')",
        (OLD.encrypt("bing-key-1234"),),
    )
    db_query(database_url, "INSERT INTO users (tenant_id, google_sub, email) VALUES (1, 's2', 'b@example.com')")  # 空は対象外
    both = TokenCipher(f"{NEW_KEY},{TOKEN_KEY}")
    before = _stored(database_url)

    # --check は数えるだけ
    checked = await rekey(app.state.sessionmaker, both, write=False)
    assert [(r.target, r.total, r.old, r.broken) for r in checked] == [
        ("users.refresh_token_encrypted", 1, 1, []),
        ("bing_keys.key_encrypted", 1, 1, []),
    ]
    assert _stored(database_url) == before

    # 暗号化し直すと、新しい鍵だけで読める（古い鍵を外せる）
    await rekey(app.state.sessionmaker, both, write=True)
    new_only = TokenCipher(NEW_KEY)
    assert [new_only.decrypt(v) for v in _stored(database_url)] == ["refresh-1", "bing-key-1234"]
    assert [r.old for r in await rekey(app.state.sessionmaker, both, write=False)] == [0, 0]


async def test_rekey_writes_nothing_when_a_value_cannot_be_read(app: FastAPI, database_url: str) -> None:
    db_query(
        database_url,
        "INSERT INTO users (tenant_id, google_sub, email, refresh_token_encrypted) VALUES (1, 's1', 'a@example.com', %s)",
        (OLD.encrypt("refresh-1"),),
    )
    # 並べていない鍵で暗号化した値（古い鍵を並べ忘れたときと同じ）
    [(key_id,)] = db_query(
        database_url,
        "INSERT INTO bing_keys (tenant_id, name, key_encrypted, last4) VALUES (1, 'k', %s, '1234') RETURNING id",
        (TokenCipher(Fernet.generate_key().decode()).encrypt("bing-key-1234"),),
    )
    before = _stored(database_url)
    results = await rekey(app.state.sessionmaker, TokenCipher(f"{NEW_KEY},{TOKEN_KEY}"), write=True)
    assert results[1].broken == [key_id]
    assert _stored(database_url) == before  # 読める値も書き換えない

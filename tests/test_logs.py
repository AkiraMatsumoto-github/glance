"""秘密の値を、設定の表示とログに出さない（glance/config.py・glance/logs.py）。"""

import logging

from fastapi import FastAPI

from glance.logs import SECRET_LOGGERS, HideCallbackQuery
from tests.conftest import TOKEN_KEY, make_settings


def test_settings_hide_secrets() -> None:
    # 失敗したときに本物の値が出ないよう、ダミーの値で確かめる
    settings = make_settings("postgresql+psycopg://glance:db-password-x@localhost/glance", google_client_secret="client-secret-x")
    shown = repr(settings) + str(settings) + str(settings.model_dump())
    for secret in ("db-password-x", "client-secret-x", TOKEN_KEY):
        assert secret not in shown
    assert settings.token_key.get_secret_value() == TOKEN_KEY


def test_secret_logs_are_quiet(app: FastAPI) -> None:
    # API を起動すると、秘密を書き得るライブラリのログは、DEBUG にしても WARNING 以上だけになる
    for name in (*SECRET_LOGGERS, "google.auth.transport.requests", "requests_oauthlib.oauth2_session"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


def _access_log(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:5000", "GET", path, "1.1", 303), None
    )


def test_callback_query_is_hidden_in_access_log(app: FastAPI) -> None:
    assert any(isinstance(f, HideCallbackQuery) for f in logging.getLogger("uvicorn.access").filters)
    record = _access_log("/api/auth/callback?state=s-x&code=code-x")
    assert HideCallbackQuery().filter(record)
    assert record.getMessage() == '127.0.0.1:5000 - "GET /api/auth/callback?… HTTP/1.1" 303'
    # ほかの URL はそのまま
    other = _access_log("/api/seo?period=last_7_days")
    HideCallbackQuery().filter(other)
    assert "period=last_7_days" in other.getMessage()

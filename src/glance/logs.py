"""ログに秘密の値を出さない（technical_design.md §9。2026-11-28 セキュリティレビューの対応）。

API とコマンドを起動するときに quiet_secret_logs() を呼ぶ。ログの段階を DEBUG にしても、次のものは出さない。
- httpx: 要求の URL を INFO で書く。Bing のキーは URL（クエリ文字列）で送るので、WARNING 以上だけにする。
- requests_oauthlib・oauthlib: DEBUG で、トークンを取る要求の本文（クライアントシークレット・認可コード）と、
  応答（更新トークン）を書く。
- google: Google の SDK は DEBUG で、要求のヘッダー（アクセストークン）を書く。
- uvicorn のアクセスログ: ログインの戻り（/api/auth/callback）の URL にある、認可コードと state を伏せる。
"""

import logging

SECRET_LOGGERS = ("httpx", "requests_oauthlib", "oauthlib", "google")
CALLBACK_PATH = "/api/auth/callback"


class HideCallbackQuery(logging.Filter):
    """uvicorn のアクセスログの、ログインの戻りの URL からクエリ文字列を外す。"""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn のアクセスログの引数は（接続元, メソッド, パスとクエリ, HTTP の版, 状態）
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and str(args[2]).startswith(CALLBACK_PATH + "?"):
            record.args = (*args[:2], CALLBACK_PATH + "?…", *args[3:])
        return True


def quiet_secret_logs() -> None:
    for name in SECRET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, HideCallbackQuery) for f in access.filters):
        access.addFilter(HideCallbackQuery())

"""Google ログイン（OAuth）の行き来（technical_design.md §4）。

Google への通信はブロッキングなので、呼ぶ側でスレッドに逃がす（asyncio.to_thread）。
テストでは exchange_code と verify_id_token を差し替える。
"""

import os
from dataclasses import dataclass
from typing import Any

import google.auth.transport.requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

from glance.config import Settings

# Google は、許可した範囲を別の書き方（openid email … や、以前に許可した範囲を足したもの）で返す。
# 頼んだ範囲と並びが違っても止めないようにする
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
CALLBACK_PATH = "/api/auth/callback"


def _flow(settings: Settings, state: str | None = None, code_verifier: str | None = None) -> Flow:
    config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret.get_secret_value(),
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
        }
    }
    return Flow.from_client_config(
        config,
        scopes=SCOPES,
        state=state,
        redirect_uri=settings.public_url + CALLBACK_PATH,
        code_verifier=code_verifier,
        autogenerate_code_verifier=code_verifier is None,
    )


@dataclass(frozen=True)
class AuthStart:
    url: str
    state: str
    code_verifier: str


def start_login(settings: Settings, force_consent: bool) -> AuthStart:
    """同意画面の URL を作る。state と PKCE の code_verifier はクッキーに入れて、戻ってきたときに照合する。"""
    flow = _flow(settings)
    options: dict[str, str] = {"access_type": "offline", "include_granted_scopes": "true"}
    if force_consent:
        # 2回目以降の同意では、Google は更新トークンを返さない。もらい直すときは同意画面を必ず出す
        options["prompt"] = "consent"
    url, state = flow.authorization_url(**options)
    assert flow.code_verifier is not None
    return AuthStart(url=url, state=state, code_verifier=flow.code_verifier)


@dataclass(frozen=True)
class Tokens:
    refresh_token: str | None
    id_token: str
    scopes: list[str]


def exchange_code(settings: Settings, state: str, code_verifier: str, code: str) -> Tokens:
    """認可コードをトークンに替える（ブロッキング）。"""
    flow = _flow(settings, state=state, code_verifier=code_verifier)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return Tokens(
        refresh_token=credentials.refresh_token,
        id_token=credentials.id_token,  # type: ignore[attr-defined]
        scopes=list(credentials.scopes or []),
    )


# サーバーの時計と Google の時計のずれを、ここまで認める。既定の0秒だと、こちらの時計が1秒遅れているだけで
# 「発行時刻より前」として断られる（2026-11-28、手元の WSL で起きた）。トークンの期限は1時間なので、安全性はほぼ変わらない
CLOCK_SKEW_SECONDS = 10


def verify_id_token(settings: Settings, token: str) -> dict[str, Any]:
    """ID トークンの署名・発行元・宛先・期限を確かめる（ブロッキング。Google の公開鍵を取りに行く）。"""
    return id_token.verify_oauth2_token(
        token,
        google.auth.transport.requests.Request(),
        settings.google_client_id,
        clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
    )

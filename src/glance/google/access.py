"""ログイン中の利用者の権限で Google（GA4・Search Console）を呼ぶクライアントを取る。"""

from fastapi import Request

from glance.db.models import User
from glance.errors import AppError
from glance.google.client import GoogleClient, ReauthRequired


def reauth_error() -> AppError:
    return AppError(401, "reauth_required", "Google の許可が切れました。ログインし直してください")


def google_client(request: Request, user: User) -> GoogleClient:
    try:
        return request.app.state.google_factory(user)
    except ReauthRequired as e:
        # 更新トークンを持っていない（フェイクのログインの後など）。Google でログインし直してもらう
        raise reauth_error() from e

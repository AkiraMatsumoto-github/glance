"""ログインのクッキー（technical_design.md §4）。

本番（https）では名前に __Host- を付ける。__Host- のクッキーは Secure・Path=/・Domain なしでしか置けないので、
同じ親ドメインのほかのサブドメイン（乗っ取られたものなど）から、同じ名前のクッキーを差し込まれない
（セッションの押しつけや、ログインの state の書き換えを防ぐ。2026-11-28 セキュリティレビューの対応）。
手元（http://localhost）は Secure にできないので付けない。どのクッキーも HttpOnly・SameSite=Lax・Path=/。
"""

from fastapi import Request, Response

SESSION = "glance_session"  # ログインのセッション（30日）
OAUTH_STATE = "glance_oauth_state"  # Google の同意画面から戻るまで（10分）
OAUTH_VERIFIER = "glance_oauth_verifier"


def _secure(request: Request) -> bool:
    return request.app.state.settings.secure_cookies


def cookie_name(name: str, secure: bool) -> str:
    return f"__Host-{name}" if secure else name


def read_cookie(request: Request, name: str) -> str | None:
    return request.cookies.get(cookie_name(name, _secure(request)))


def set_cookie(request: Request, response: Response, name: str, value: str, max_age: int) -> None:
    secure = _secure(request)
    response.set_cookie(
        cookie_name(name, secure), value, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/"
    )


def delete_cookie(request: Request, response: Response, name: str) -> None:
    secure = _secure(request)
    response.delete_cookie(cookie_name(name, secure), path="/", httponly=True, secure=secure, samesite="lax")

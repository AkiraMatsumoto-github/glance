"""FastAPI の起動。/api と、画面（Next.js で書き出した静的ファイル）をまとめて出す（technical_design.md §1）。

起動: uv run uvicorn glance.main:create_app --factory --host 127.0.0.1 --port 8101
"""

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from glance.auth.crypto import TokenCipher
from glance.auth.routes import router as auth_router
from glance.bing.client import BingClient, FakeBingClient, RealBingClient
from glance.bing.routes import router as bing_router
from glance.config import Settings
from glance.db.session import create_engine, create_sessionmaker
from glance.errors import AppError, app_error_handler
from glance.google.factory import GoogleFactory, default_google_factory
from glance.logs import quiet_secret_logs
from glance.realtime.routes import router as realtime_router
from glance.realtime.service import SITE_TIMEOUT_SECONDS
from glance.seo.routes import router as seo_router
from glance.sites.links import router as links_router
from glance.sites.routes import router as sites_router

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# 書き込みの本文の上限。本文はログインの確認より先に読まれるので、ログインしていない人の大きな本文を断る
MAX_BODY_BYTES = 64 * 1024
# 全部の応答（画面・API）に付ける。ほかのサイトのフレームに埋め込ませない（クリックを盗む攻撃を防ぐ）。
# 送ったファイルの種類を、ブラウザに推測させない（2026-11-28 セキュリティレビューの対応）
SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
}


class PageFiles(StaticFiles):
    """静的書き出しの画面を出す。/login のような URL は login.html を返す。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code != 404:
                raise
            response = None
        if (response is None or response.status_code == 404) and path not in ("", ".") and not path.endswith(".html"):
            try:
                html = await super().get_response(f"{path.rstrip('/')}.html", scope)
                if html.status_code == 200:
                    return html
            except HTTPException:
                pass
        if response is None:
            raise HTTPException(status_code=404)
        return response


def create_app(
    settings: Settings | None = None,
    google_factory: GoogleFactory | None = None,
    realtime_timeout: float = SITE_TIMEOUT_SECONDS,
    bing_client: BingClient | None = None,
) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    settings.check()
    quiet_secret_logs()

    app = FastAPI(title="Glance", docs_url=None, redoc_url=None, openapi_url=None)
    engine = create_engine(settings.database_url.get_secret_value())
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    # 更新トークンの暗号化（フェイクモードで鍵がないときは使わない）
    token_key = settings.token_key.get_secret_value()
    app.state.cipher = TokenCipher(token_key) if token_key else None
    app.state.google_factory = google_factory or default_google_factory(settings, app.state.cipher)
    app.state.realtime_timeout = realtime_timeout
    # Bing は API キーで呼ぶ（利用者ごとのクライアントは要らない）。フェイクモードではダミー
    app.state.bing_client = bing_client or (FakeBingClient() if settings.fake_google else RealBingClient())

    app.add_exception_handler(AppError, app_error_handler)

    @app.middleware("http")
    async def api_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        is_api = request.url.path.startswith("/api/")
        # 書き込みの要求は JSON だけを受ける。SameSite=Lax のクッキーと合わせて、別のサイトからの書き込みを防ぐ
        if is_api and request.method in WRITE_METHODS:
            content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type != "application/json":
                return JSONResponse(
                    {"code": "unsupported_media_type", "message": "JSON で送ってください"}, status_code=415
                )
            # 長さの分からない（分割して送る）本文も、読まずに断る
            length = request.headers.get("content-length")
            chunked = "chunked" in request.headers.get("transfer-encoding", "").lower()
            if (length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES)) or (length is None and chunked):
                return JSONResponse({"code": "payload_too_large", "message": "送る内容が大きすぎます"}, status_code=413)
        response = await call_next(request)
        if is_api:
            response.headers["Cache-Control"] = "no-store"
        return response

    # 後に足したものが外側になる。api_guard が断った応答（415・413）にも付ける
    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    app.include_router(auth_router)
    app.include_router(sites_router)
    app.include_router(links_router)
    app.include_router(bing_router)
    app.include_router(realtime_router)
    app.include_router(seo_router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_not_found(path: str) -> JSONResponse:
        return JSONResponse({"code": "not_found", "message": "見つかりません"}, status_code=404)

    static_dir = Path(settings.static_dir)
    if static_dir.is_dir():
        app.mount("/", PageFiles(directory=static_dir, html=True), name="web")

    return app

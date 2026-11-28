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
from glance.config import Settings
from glance.db.session import create_engine, create_sessionmaker
from glance.errors import AppError, app_error_handler
from glance.google.factory import GoogleFactory, default_google_factory
from glance.realtime.routes import router as realtime_router
from glance.realtime.service import SITE_TIMEOUT_SECONDS
from glance.seo.routes import router as seo_router
from glance.sites.links import router as links_router
from glance.sites.routes import router as sites_router

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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

    app = FastAPI(title="Glance", docs_url=None, redoc_url=None, openapi_url=None)
    engine = create_engine(settings.database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    # 更新トークンの暗号化（フェイクモードで鍵がないときは使わない）
    app.state.cipher = TokenCipher(settings.token_key) if settings.token_key else None
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
        response = await call_next(request)
        if is_api:
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(auth_router)
    app.include_router(sites_router)
    app.include_router(links_router)
    app.include_router(realtime_router)
    app.include_router(seo_router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_not_found(path: str) -> JSONResponse:
        return JSONResponse({"code": "not_found", "message": "見つかりません"}, status_code=404)

    static_dir = Path(settings.static_dir)
    if static_dir.is_dir():
        app.mount("/", PageFiles(directory=static_dir, html=True), name="web")

    return app

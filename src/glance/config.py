"""環境変数の読み込み（technical_design.md §9）。

手元では .env、本番では systemd が /etc/glance/glance.env から渡す。
"""

from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_URL_PREFIXES = ("http://localhost", "http://127.0.0.1")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GLANCE_", env_file=".env", extra="ignore")

    database_url: str
    allowed_emails: str = ""
    public_url: str = ""
    fake_google: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    token_key: str = ""
    # 画面（Next.js で書き出した静的ファイル）の置き場所。無ければ API だけを出す
    static_dir: str = "web/out"

    @cached_property
    def allowed_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    def check(self) -> None:
        """起動してはいけない組み合わせを止める。"""
        if self.fake_google:
            if self.public_url and not self.public_url.startswith(LOCAL_URL_PREFIXES):
                raise ValueError(
                    "GLANCE_FAKE_GOOGLE は手元でだけ使える（GLANCE_PUBLIC_URL が http://localhost か http://127.0.0.1 のとき）"
                )
            return
        # Google ログインに要る値
        missing = [
            name
            for name, value in (
                ("GLANCE_GOOGLE_CLIENT_ID", self.google_client_id),
                ("GLANCE_GOOGLE_CLIENT_SECRET", self.google_client_secret),
                ("GLANCE_TOKEN_KEY", self.token_key),
                ("GLANCE_PUBLIC_URL", self.public_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Google ログインに要る環境変数が空です: {', '.join(missing)}")

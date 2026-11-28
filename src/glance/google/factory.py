"""利用者ごとの Google（GA4・Search Console）のクライアントを作る。"""

from collections.abc import Callable

from glance.auth.crypto import TokenCipher
from glance.config import Settings
from glance.db.models import User
from glance.google.fake import FakeGoogleClient
from glance.google.client import GoogleClient, ReauthRequired
from glance.google.real import RealGoogleClient, make_credentials

GoogleFactory = Callable[[User], GoogleClient]


def default_google_factory(settings: Settings, cipher: TokenCipher | None) -> GoogleFactory:
    if settings.fake_google:
        fake = FakeGoogleClient()
        return lambda _user: fake

    assert cipher is not None
    # 利用者ごとに、認証情報（アクセストークンを持つ）とクライアントを使い回す。
    # 更新トークンが入れ替わったら（ログインし直したら）作り直す
    cache: dict[int, tuple[str, RealGoogleClient]] = {}

    def factory(user: User) -> GoogleClient:
        encrypted = user.refresh_token_encrypted
        if not encrypted:
            raise ReauthRequired()
        cached = cache.get(user.id)
        if cached and cached[0] == encrypted:
            return cached[1]
        credentials = make_credentials(
            cipher.decrypt(encrypted), settings.google_client_id, settings.google_client_secret.get_secret_value()
        )
        client = RealGoogleClient(credentials)
        cache[user.id] = (encrypted, client)
        return client

    return factory

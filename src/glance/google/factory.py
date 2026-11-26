"""利用者ごとの GA4 クライアントを作る。"""

from collections.abc import Callable

from glance.auth.crypto import TokenCipher
from glance.config import Settings
from glance.db.models import User
from glance.google.fake import FakeGa4Client
from glance.google.ga4 import Ga4Client, ReauthRequired
from glance.google.real import RealGa4Client, make_credentials

Ga4Factory = Callable[[User], Ga4Client]


def default_ga4_factory(settings: Settings, cipher: TokenCipher | None) -> Ga4Factory:
    if settings.fake_google:
        fake = FakeGa4Client()
        return lambda _user: fake

    assert cipher is not None
    # 利用者ごとに、認証情報（アクセストークンを持つ）とクライアントを使い回す。
    # 更新トークンが入れ替わったら（ログインし直したら）作り直す
    cache: dict[int, tuple[str, RealGa4Client]] = {}

    def factory(user: User) -> Ga4Client:
        encrypted = user.refresh_token_encrypted
        if not encrypted:
            raise ReauthRequired()
        cached = cache.get(user.id)
        if cached and cached[0] == encrypted:
            return cached[1]
        credentials = make_credentials(
            cipher.decrypt(encrypted), settings.google_client_id, settings.google_client_secret
        )
        client = RealGa4Client(credentials)
        cache[user.id] = (encrypted, client)
        return client

    return factory

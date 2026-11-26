"""利用者ごとの GA4 クライアントを作る。"""

from collections.abc import Callable

from glance.config import Settings
from glance.db.models import User
from glance.google.fake import FakeGa4Client
from glance.google.ga4 import Ga4Client, Ga4NotConfigured

Ga4Factory = Callable[[User], Ga4Client]


def default_ga4_factory(settings: Settings) -> Ga4Factory:
    fake = FakeGa4Client()

    def factory(_user: User) -> Ga4Client:
        if settings.fake_google:
            return fake
        # 本物の GA4（利用者の更新トークンで呼ぶ）は、2番目の段階で Google ログインをつないでから作る
        raise Ga4NotConfigured()

    return factory

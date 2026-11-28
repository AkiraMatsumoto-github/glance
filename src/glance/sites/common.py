"""サイト設定の API で共通に使う部品。"""

from glance.auth.deps import Db
from glance.db.models import Site
from glance.errors import AppError


async def tenant_site(db: Db, tenant_id: int, site_id: int) -> Site:
    """ログイン中の利用者の顧客のサイト。ほかの顧客のサイトは、無いのと同じに扱う。"""
    site = await db.get(Site, site_id)
    if site is None or site.tenant_id != tenant_id:
        raise AppError(404, "not_found", "サイトが見つかりません")
    return site

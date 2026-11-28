"""Search Console のサイトの一覧と、GA4 のプロパティと同じドメインのサイトの選び方（data_sources.md §3）。

サイトの追加（sites/routes.py）と紐づけ（sites/links.py）で使う。取れないときは、理由を画面に出せるエラーにする。
"""

from urllib.parse import urlsplit

from glance.errors import AppError
from glance.google.access import reauth_error
from glance.google.client import (
    GoogleClient,
    GooglePermissionDenied,
    GoogleQuotaExceeded,
    GoogleUnavailable,
    GscApiDisabled,
    ReauthRequired,
)


def _bare(host: str) -> str:
    return host.lower().removeprefix("www.")


def match_gsc_site(hosts: list[str], sites: list[str]) -> str | None:
    """GA4 のホストと同じドメインの Search Console のサイト（data_sources.md §3）。

    ドメインのプロパティ（sc-domain:）があればそれ（いくつか合うときは、いちばん細かいドメイン）。
    なければ、同じホスト（www. の有無は問わない）の URL のプロパティが1つだけあるときにそれ。どちらもなければ None。
    """
    names = {host.lower() for host in hosts}
    domains = [
        site
        for site in sites
        if site.startswith("sc-domain:")
        and any(name == site.removeprefix("sc-domain:") or name.endswith("." + site.removeprefix("sc-domain:")) for name in names)
    ]
    if domains:
        return max(domains, key=len)
    bare = {_bare(name) for name in names}
    prefixes = [site for site in sites if not site.startswith("sc-domain:") and _bare(urlsplit(site).hostname or "") in bare]
    return prefixes[0] if len(prefixes) == 1 else None


async def gsc_sites(client: GoogleClient) -> list[str]:
    """ログインしたアカウントが見られる Search Console のサイト。取れなければ、理由を画面に出せるエラーにする。"""
    try:
        return await client.list_gsc_sites()
    except ReauthRequired as e:
        raise reauth_error() from e
    except GscApiDisabled as e:
        raise AppError(
            503, "gsc_api_disabled", "Search Console API が有効になっていません。GCP のプロジェクトで有効にしてください"
        ) from e
    except GooglePermissionDenied as e:
        raise AppError(403, "permission_denied", "Search Console のサイトの一覧を見る権限がありません") from e
    except GoogleQuotaExceeded as e:
        raise AppError(429, "gsc_quota", "Search Console の呼び出しの上限に当たりました。少し待ってから試してください") from e
    except GoogleUnavailable as e:
        raise AppError(502, "gsc_unavailable", "Search Console に接続できませんでした。時間をおいて試してください") from e


async def ensure_gsc_site(client: GoogleClient, site_url: str) -> None:
    """紐づけようとしている Search Console のサイトが、ログインしたアカウントで見られるか確かめる。"""
    if site_url not in await gsc_sites(client):
        raise AppError(400, "unknown_gsc_site", "このアカウントで見られない Search Console のサイトです")


async def suggested_gsc_site(client: GoogleClient, property_id: str | None, sites: list[str]) -> str | None:
    """GA4 のプロパティと同じドメインのサイト。取れなければ（上限・接続の失敗も）おすすめなしにする。"""
    if not property_id:
        return None
    try:
        hosts = await client.web_stream_hosts(property_id)
    except (GooglePermissionDenied, GoogleQuotaExceeded, GoogleUnavailable):
        return None
    except ReauthRequired as e:
        raise reauth_error() from e
    return match_gsc_site(hosts, sites)

"""デモのサイト設定のダミー（screen_design.md §4・§6、technical_design.md §6.4）。

サイトは「デモサイト A〜E」。Search Console と Bing を紐づけ済みにする（Bing のキーは1つ）。
「デモサイト F」は、まだ追加していない GA4 のプロパティで、Search Console のサイトが見つからない例。
ドメインの .example は、例のために取ってあるもので実在しない。DB・Google・Bing・利用者のデータには触れない。
"""

from glance.errors import AppError
from glance.google.fake import DEMO_SITES

NOT_ADDED = ("900000006", "デモサイト F")

# GA4 のプロパティ（のウェブのデータストリーム）のドメイン
_DOMAINS = {pid: f"demo-{name[-1].lower()}.example" for pid, name in [*DEMO_SITES, NOT_ADDED]}

# ログインしたアカウントが見られる Search Console のサイト。F のドメインのものはない。
# ほかのドメインと合わない URL のサイトも1つ置き、選ぶ一覧に出る例にする
GSC_SITES = [f"sc-domain:{_DOMAINS[pid]}" for pid, _ in DEMO_SITES] + ["https://blog.demo-a.example/"]

# 保存済みの Bing のキー（名前と末尾4文字だけ）と、そのキーで見られるサイト
BING_KEYS = [{"id": 1, "name": "デモのキー", "last4": "demo"}]
BING_SITES = [f"https://{_DOMAINS[pid]}/" for pid, _ in DEMO_SITES]


def sites() -> list[dict]:
    return [
        {
            "id": i + 1,
            "name": name,
            "ga4_property_id": pid,
            "links": {
                "gsc_site_url": f"sc-domain:{_DOMAINS[pid]}",
                "bing_site_url": f"https://{_DOMAINS[pid]}/",
                "bing_key_id": 1,
            },
        }
        for i, (pid, name) in enumerate(DEMO_SITES)
    ]


def _gsc_match(property_id: str) -> str | None:
    # GA4 のドメインと同じドメインの Search Console のサイト（ドメインのプロパティ）
    site = f"sc-domain:{_DOMAINS[property_id]}"
    return site if site in GSC_SITES else None


def accounts() -> list[dict]:
    properties = [
        {"property_id": pid, "name": name, "added": True, "search_console": None} for pid, name in DEMO_SITES
    ]
    pid, name = NOT_ADDED
    properties.append(
        {
            "property_id": pid,
            "name": name,
            "added": False,
            "search_console": {"site_url": _gsc_match(pid), "candidates": GSC_SITES},
        }
    )
    return [{"account_id": "800000001", "name": "デモのアカウント", "properties": properties}]


def gsc_choice(site_id: int) -> dict:
    site = next((s for s in sites() if s["id"] == site_id), None)
    if site is None:
        raise AppError(404, "not_found", "サイトが見つかりません")
    return {
        "current": site["links"]["gsc_site_url"],
        "suggested": _gsc_match(site["ga4_property_id"]),
        "candidates": GSC_SITES,
    }

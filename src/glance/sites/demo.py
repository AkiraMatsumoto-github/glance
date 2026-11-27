"""デモのサイト設定のダミー（screen_design.md §4・§6、technical_design.md §6.4）。

サイトは「デモサイト A〜E」。Google（GA4・Search Console）と Bing を紐づけ済みにする。
「デモサイト F」は、まだ追加していない GA4 のプロパティで、Search Console のサイトが見つからない例。
ドメインの .example は、例のために取ってあるもので実在しない。DB・Google・Bing・利用者のデータには触れない。
"""

from glance.google.fake import DEMO_SITES

TIMEZONE = "Asia/Tokyo"
NOT_ADDED = ("900000006", "デモサイト F")

# GA4 のプロパティ（のウェブのデータストリーム）のドメイン
_DOMAINS = {pid: f"demo-{name[-1].lower()}.example" for pid, name in [*DEMO_SITES, NOT_ADDED]}

# ログインしたアカウントが見られる Search Console のサイト。F のドメインのものはない。
# ほかのドメインと合わない URL のサイトも1つ置き、選ぶ一覧に出る例にする
GSC_SITES = [f"sc-domain:{_DOMAINS[pid]}" for pid, _ in DEMO_SITES] + ["https://blog.demo-a.example/"]

# 保存済みの API キーで見られる Bing のサイト
BING_SITES = [f"https://{_DOMAINS[pid]}/" for pid, _ in DEMO_SITES]


def sites() -> list[dict]:
    return [
        {
            "id": i + 1,
            "name": name,
            "sort_order": i,
            "timezone": TIMEZONE,
            "ga4_property_id": pid,
            "links": {"gsc_site_url": f"sc-domain:{_DOMAINS[pid]}", "bing_site_url": f"https://{_DOMAINS[pid]}/"},
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


def bing() -> dict:
    return {"key_saved": True, "sites": BING_SITES}

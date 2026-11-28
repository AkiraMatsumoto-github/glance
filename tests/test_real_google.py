"""本物の Google のクライアント（GA4・Search Console）の、応答の読み取りとエラーの変換（Google の応答は作って渡す）。"""

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.analytics.data_v1beta import RunRealtimeReportResponse
from google.api_core import exceptions as api_errors
from google.auth.exceptions import RefreshError

from glance.auth.crypto import TokenCipher
from glance.google.client import GooglePermissionDenied, GoogleQuotaExceeded, GoogleUnavailable, GscApiDisabled, ReauthRequired
from glance.google.real import RealGoogleClient


class ValidCredentials:
    valid = True


class ExpiredCredentials:
    valid = False

    def refresh(self, request: Any) -> None:
        raise RefreshError("invalid_grant: Token has been expired or revoked.")


def response(rows: list[tuple[list[str], list[str]]]) -> RunRealtimeReportResponse:
    return RunRealtimeReportResponse(
        rows=[
            {"dimension_values": [{"value": d} for d in dims], "metric_values": [{"value": m} for m in metrics]}
            for dims, metrics in rows
        ]
    )


class DataStub:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.requests: list[Any] = []

    async def run_realtime_report(self, request: Any) -> Any:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def client(data: Any = None, admin: Any = None, credentials: Any = None) -> RealGoogleClient:
    return RealGoogleClient(credentials or ValidCredentials(), data_client=data or DataStub(None), admin_client=admin or object())  # type: ignore[arg-type]


async def test_totals() -> None:
    data = DataStub(response([([], ["120", "45", "2"])]))
    totals = await client(data).realtime_totals("123")
    assert (totals.page_views, totals.active_users, totals.key_events) == (120, 45, 2)
    request = data.requests[0]
    assert request.property == "properties/123"
    assert [m.name for m in request.metrics] == ["screenPageViews", "activeUsers", "keyEvents"]


async def test_totals_with_no_rows_is_zero() -> None:
    totals = await client(DataStub(response([]))).realtime_totals("123")
    assert (totals.page_views, totals.active_users, totals.key_events) == (0, 0, 0)


async def test_per_minute_reads_minutes_ago() -> None:
    data = DataStub(response([(["00"], ["5", "3"]), (["12"], ["2", "2"])]))
    rows = await client(data).realtime_per_minute("123")
    assert [(r.minutes_ago, r.page_views, r.active_users) for r in rows] == [(0, 5, 3), (12, 2, 2)]
    assert data.requests[0].dimensions[0].name == "minutesAgo"


async def test_top_pages_by_pv_and_breakdown_by_uu() -> None:
    data = DataStub(response([(["記事 A"], ["12", "8"])]))
    pages = await client(data).realtime_top_pages("123", 20)
    assert pages[0].title == "記事 A" and pages[0].page_views == 12
    request = data.requests[0]
    assert request.limit == 20
    assert request.order_bys[0].metric.metric_name == "screenPageViews" and request.order_bys[0].desc
    data = DataStub(response([(["JP"], ["37"])]))
    rows = await client(data).realtime_breakdown("123", "countryId", 10)
    assert (rows[0].key, rows[0].active_users) == ("JP", 37)
    request = data.requests[0]
    assert [m.name for m in request.metrics] == ["activeUsers"]
    assert request.order_bys[0].metric.metric_name == "activeUsers"


async def test_events_by_count() -> None:
    data = DataStub(response([(["page_view"], ["120"]), (["cta_click"], ["4"])]))
    rows = await client(data).realtime_events("123", 20)
    assert [(r.name, r.event_count) for r in rows] == [("page_view", 120), ("cta_click", 4)]
    request = data.requests[0]
    assert request.dimensions[0].name == "eventName"
    assert [m.name for m in request.metrics] == ["eventCount"]
    assert request.order_bys[0].metric.metric_name == "eventCount" and request.limit == 20


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (api_errors.PermissionDenied("no"), GooglePermissionDenied),
        (api_errors.NotFound("no"), GooglePermissionDenied),
        (api_errors.ResourceExhausted("quota"), GoogleQuotaExceeded),
        (api_errors.ServiceUnavailable("down"), GoogleUnavailable),
        (api_errors.DeadlineExceeded("slow"), GoogleUnavailable),
        (api_errors.Unauthenticated("expired"), ReauthRequired),
    ],
)
async def test_errors_are_mapped(error: Exception, expected: type[Exception]) -> None:
    with pytest.raises(expected):
        await client(DataStub(error)).realtime_totals("123")


async def test_revoked_refresh_token_needs_reauth() -> None:
    with pytest.raises(ReauthRequired):
        await client(DataStub(response([])), credentials=ExpiredCredentials()).realtime_totals("123")


class Pager:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    def __aiter__(self) -> Any:
        async def gen() -> Any:
            for item in self.items:
                yield item

        return gen()


async def test_admin_reads_accounts_and_property() -> None:
    class AdminStub:
        async def list_account_summaries(self) -> Pager:
            return Pager(
                [
                    SimpleNamespace(
                        account="accounts/800",
                        display_name="アカウント",
                        property_summaries=[SimpleNamespace(property="properties/900", display_name="LogiShift")],
                    )
                ]
            )

        async def get_property(self, name: str) -> Any:
            assert name == "properties/900"
            return SimpleNamespace(display_name="LogiShift", time_zone="Asia/Tokyo")

    c = client(admin=AdminStub())
    accounts = await c.list_account_summaries()
    assert accounts[0].account_id == "800" and accounts[0].properties[0].property_id == "900"
    info = await c.get_property("900")
    assert (info.name, info.time_zone) == ("LogiShift", "Asia/Tokyo")


def test_token_cipher_rotation() -> None:
    from cryptography.fernet import Fernet

    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    encrypted = TokenCipher(old).encrypt("secret")
    rotated = TokenCipher(f"{new},{old}")
    assert rotated.decrypt(encrypted) == "secret"
    assert TokenCipher(new).decrypt(rotated.encrypt("secret")) == "secret"


# --- ウェブのデータストリームと Search Console のサイトの一覧 ---------------------------------


class StreamsAdmin:
    def __init__(self, uris: list[str]) -> None:
        self.uris = uris
        self.parents: list[str] = []

    async def list_data_streams(self, parent: str) -> Pager:
        self.parents.append(parent)
        return Pager([SimpleNamespace(web_stream_data=SimpleNamespace(default_uri=uri)) for uri in self.uris])


async def test_web_stream_hosts() -> None:
    # アプリのストリーム（URL なし）は除く。スキームのない URL も読む
    admin = StreamsAdmin(["https://www.example.com", "", "shop.example.com/path"])
    assert await client(admin=admin).web_stream_hosts("123") == ["www.example.com", "shop.example.com"]
    assert admin.parents == ["properties/123"]


class TokenCredentials(ValidCredentials):
    token = "access-token"


def gsc_client(handler: Any) -> RealGoogleClient:
    return RealGoogleClient(
        TokenCredentials(),  # type: ignore[arg-type]
        data_client=DataStub(None),
        admin_client=object(),
        gsc_transport=httpx.MockTransport(handler),
    )


async def test_list_gsc_sites() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        entries = [
            {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
            {"siteUrl": "https://example.com/", "permissionLevel": "siteFullUser"},
            {"siteUrl": "https://unverified.example/", "permissionLevel": "siteUnverifiedUser"},
        ]
        return httpx.Response(200, json={"siteEntry": entries})

    # 確認していないサイトは除く
    assert await gsc_client(handler).list_gsc_sites() == ["https://example.com/", "sc-domain:example.com"]
    assert seen == ["Bearer access-token"]
    assert await gsc_client(lambda _r: httpx.Response(200, json={})).list_gsc_sites() == []


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (403, {"error": {"status": "PERMISSION_DENIED", "details": [{"reason": "SERVICE_DISABLED"}]}}, GscApiDisabled),
        (403, {"error": {"message": "Request had insufficient authentication scopes."}}, ReauthRequired),
        (401, {}, ReauthRequired),
        (403, {"error": {"message": "User does not have sufficient permission"}}, GooglePermissionDenied),
        (403, {"error": {"message": "Quota exceeded", "errors": [{"reason": "rateLimitExceeded"}]}}, GoogleQuotaExceeded),
        (429, {"error": {"message": "Quota exceeded for quota metric"}}, GoogleQuotaExceeded),
        (503, {"error": {"message": "Backend Error"}}, GoogleUnavailable),
    ],
)
async def test_list_gsc_sites_errors(status: int, body: dict, error: type[Exception]) -> None:
    with pytest.raises(error):
        await gsc_client(lambda _r: httpx.Response(status, json=body)).list_gsc_sites()


async def test_list_gsc_sites_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(GoogleUnavailable, match="ConnectTimeout"):
        await gsc_client(handler).list_gsc_sites()

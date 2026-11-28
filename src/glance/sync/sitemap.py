"""サイトマップの URL を読む（data_sources.md §3）。

Search Console に登録したサイトマップ（sitemaps.list）から始め、サイトマップの索引（sitemapindex）は中のサイトマップを
たどる。.gz にも対応する。読みすぎないよう、ファイル数・URL 数・1ファイルの大きさに上限を置く。

サーバーの内側に届かせない（technical_design.md §6.5。2026-11-28 セキュリティレビューの対応）:
- 紐づけたサイトのドメインの外は読まない。ポートは既定（80・443）だけ。転送先も1回ずつ確かめる。
- つなぐ前に名前解決し、公開の IP だけにつなぐ（ドメインの持ち主は、名前を内側の IP に向けられるため）。
XML は木を作らずに先頭から読み、loc だけを拾う（壊れた・悪意のある大きなファイルで、メモリを使いすぎないため）。
"""

import gzip
import io
import ipaddress
import socket
from collections.abc import Callable, Iterable
from typing import Protocol
from urllib.parse import urljoin, urlsplit
from xml.parsers import expat

import anyio
import httpcore
import httpx

from glance.sync.values import page_path

MAX_FILES = 500
MAX_URLS = 200_000
MAX_BYTES = 50 * 1024 * 1024  # 1ファイル（サイトマップの決まりの上限）
MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (compatible; Glance/1.0; sitemap)"


def site_domain(site_url: str) -> str:
    """紐づけた Search Console のサイトのドメイン（sc-domain:example.com・https://www.example.com/ → example.com）。"""
    host = site_url.removeprefix("sc-domain:") if site_url.startswith("sc-domain:") else urlsplit(site_url).hostname or ""
    return host.lower().removeprefix("www.")


def within(url: str, domain: str) -> bool:
    """http(s) で、ポートが既定（80・443）で、ホストがそのドメインか、そのサブドメインか。"""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:  # 数字でないポート
        return False
    return (
        parts.scheme in ("http", "https")
        and port in (None, 80, 443)
        and bool(domain)
        and (host == domain or host.endswith("." + domain))
    )


class SitemapFetcher(Protocol):
    async def fetch(self, url: str, allowed: Callable[[str], bool]) -> bytes:
        """url を読む。転送されたら、転送先が allowed のときだけ続ける。"""
        ...


def is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """インターネットの公開の住所か（ループバック・プライベート・リンクローカル・予約・マルチキャストは違う）。"""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """つなぐ前に名前解決し、全部の IP が公開のものなら、そのうちの1つにつなぐ。

    確かめた IP にそのままつなぐので、確かめた後に名前解決の結果を変えられても（DNS rebinding）内側に届かない。
    https の証明書は、元のホスト名で確かめる（httpcore が server_hostname に元のホスト名を渡す）。
    """

    def __init__(self) -> None:
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            with anyio.fail_after(timeout):
                infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (OSError, TimeoutError) as e:
            raise httpcore.ConnectError(f"名前解決できません: {host}") from e
        addresses = sorted({ipaddress.ip_address(info[4][0]) for info in infos}, key=lambda a: (a.version, str(a)))
        if not addresses or not all(is_public(a) for a in addresses):
            raise httpcore.ConnectError(f"公開されていない住所にはつなぎません: {host}")
        # IPv4 から順に試す（IPv6 でつなげない環境で、時間切れまで待たないため）
        error: Exception | None = None
        for address in addresses:
            try:
                return await self._backend.connect_tcp(
                    str(address), port, timeout=timeout, local_address=local_address, socket_options=socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as e:
                error = e
        assert error is not None
        raise error

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("サイトマップの取得では使わない")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PublicOnlyTransport(httpx.AsyncHTTPTransport):
    """公開の IP にだけつなぐ transport。

    httpx は、つなぎ方（network_backend）を外から渡す口を持たないので、中の接続の束（_pool）を作り直す。
    httpx を上げて中の作りが変わると効かなくなるので、テスト（内側の住所を断ること）で確かめる。
    """

    def __init__(self) -> None:
        super().__init__(trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False), network_backend=PublicOnlyBackend()
        )


class HttpSitemapFetcher:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # テストでは、決まった応答を返す transport に差し替える
        self._transport = transport

    async def fetch(self, url: str, allowed: Callable[[str], bool]) -> bytes:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=False,
            transport=self._transport or PublicOnlyTransport(),
            trust_env=False,  # 環境変数のプロキシを使わない（公開の IP だけにつなぐ確認を通らなくなるため）
            headers={"User-Agent": USER_AGENT},
        ) as http:
            for _ in range(MAX_REDIRECTS + 1):
                async with http.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers["location"])
                        if not allowed(url):
                            raise ValueError(f"サイトの外へ転送されました: {url}")
                        continue
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise ValueError(f"サイトマップが大きすぎます: {url}")
                    return bytes(body)
        raise ValueError(f"転送が多すぎます: {url}")


def _local(name: str) -> str:
    return name.rsplit(" ", 1)[-1]  # 名前空間（http://www.sitemaps.org/... ）を外す


def parse_sitemap(body: bytes) -> tuple[str, list[str]]:
    """サイトマップの XML から、一番外の要素の名前（urlset か sitemapindex）と、loc の中身を取る。

    木を作らずに先頭から読み、loc だけを持つ。loc が URL 数の上限を超えたら、そこで止める。
    サイトマップは実体（DTD の ENTITY）を使わないので、宣言があれば読まない（実体の展開でメモリを使わせる XML を断つ）。
    """
    parser = expat.ParserCreate(namespace_separator=" ")
    root: list[str] = []
    locs: list[str] = []
    text: list[str] | None = None  # いま読んでいる loc の中身

    def start(name: str, _attrs: object) -> None:
        nonlocal text
        if not root:
            root.append(_local(name))
        if _local(name) == "loc":
            text = []

    def end(name: str) -> None:
        nonlocal text
        if _local(name) == "loc" and text is not None:
            value = "".join(text).strip()
            text = None
            if value:
                locs.append(value)
                if len(locs) > MAX_URLS:
                    raise ValueError(f"サイトマップの URL が {MAX_URLS} を超えました")

    def chars(data: str) -> None:
        if text is not None:
            text.append(data)

    def entity(*_args: object) -> None:
        raise ValueError("サイトマップに実体の宣言があるので読みません")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.EntityDeclHandler = entity
    parser.Parse(body, True)
    return (root[0] if root else ""), locs


async def sitemap_paths(fetcher: SitemapFetcher, sitemaps: Iterable[str], site_url: str) -> set[str]:
    """サイトマップに載っているページのパス。索引（sitemapindex）は中をたどる。

    site_url（紐づけた Search Console のサイト）のドメインの外のサイトマップは読まない。1つも読めなければ失敗にする
    （サイトマップの URL を空で入れ替えないため）。
    """
    domain = site_domain(site_url)

    def allowed(url: str) -> bool:
        return within(url, domain)

    queue, seen, paths = list(sitemaps), set[str](), set[str]()
    while queue:
        url = queue.pop(0)
        if url in seen or not allowed(url):
            continue
        seen.add(url)
        if len(seen) > MAX_FILES:
            raise ValueError(f"サイトマップのファイルが {MAX_FILES} を超えました")
        body = await fetcher.fetch(url, allowed)
        if body[:2] == b"\x1f\x8b":  # .gz。展開した後の大きさにも上限を置く
            body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError(f"サイトマップが大きすぎます: {url}")
        root, locs = parse_sitemap(body)
        if root == "sitemapindex":
            queue.extend(locs)  # 中のサイトマップ
        elif root == "urlset":
            paths.update(page_path(loc) for loc in locs)
        if len(paths) > MAX_URLS:
            raise ValueError(f"サイトマップの URL が {MAX_URLS} を超えました")
    if not seen:
        raise ValueError(f"{domain} の中にあるサイトマップがありません（サイトの外にあるサイトマップは読みません）")
    return paths


# 手元（GLANCE_FAKE_GOOGLE=1）とテストで使うダミー。索引→2つのサイトマップの形にし、
# 検索に出ているページ（fake.py の Search Console のページ）と、出ていないページを混ぜる
FAKE_PAGES = ["/", "/glossary/wms/", "/news/2024-problem/", "/tools/%E5%80%89%E5%BA%AB/", "/glossary/amr/", "/case/picking/"]


class FakeSitemapFetcher:
    async def fetch(self, url: str, allowed: Callable[[str], bool]) -> bytes:
        base = url.rsplit("/", 1)[0]
        ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
        if url.endswith("sitemap_index.xml"):
            items = "".join(f"<sitemap><loc>{base}/{name}</loc></sitemap>" for name in ("page-sitemap.xml", "post-sitemap.xml"))
            return f'<?xml version="1.0"?><sitemapindex {ns}>{items}</sitemapindex>'.encode()
        pages = FAKE_PAGES[:3] if url.endswith("page-sitemap.xml") else FAKE_PAGES[3:]
        items = "".join(f"<url><loc>{base}{path}</loc></url>" for path in pages)
        return f'<?xml version="1.0"?><urlset {ns}>{items}</urlset>'.encode()

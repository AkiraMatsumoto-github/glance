"""サイトマップの URL を読む（data_sources.md §3）。

Search Console に登録したサイトマップ（sitemaps.list）から始め、サイトマップの索引（sitemapindex）は中のサイトマップを
たどる。.gz にも対応する。読みすぎないよう、ファイル数・URL 数・1ファイルの大きさに上限を置く。
"""

import gzip
import io
from collections.abc import Iterable
from typing import Protocol
from xml.etree import ElementTree

import httpx

from glance.sync.values import page_path

MAX_FILES = 500
MAX_URLS = 200_000
MAX_BYTES = 50 * 1024 * 1024  # 1ファイル（サイトマップの決まりの上限）
USER_AGENT = "Mozilla/5.0 (compatible; Glance/1.0; sitemap)"


class SitemapFetcher(Protocol):
    async def fetch(self, url: str) -> bytes: ...


class HttpSitemapFetcher:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def fetch(self, url: str) -> bytes:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, transport=self._transport, headers={"User-Agent": USER_AGENT}
        ) as http:
            async with http.stream("GET", url) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError(f"サイトマップが大きすぎます: {url}")
                return bytes(body)


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # 名前空間（{http://www.sitemaps.org/...}）を外す


async def sitemap_paths(fetcher: SitemapFetcher, sitemaps: Iterable[str]) -> set[str]:
    """サイトマップに載っているページのパス。索引（sitemapindex）は中をたどる。"""
    queue, seen, paths = list(sitemaps), set[str](), set[str]()
    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if len(seen) > MAX_FILES:
            raise ValueError(f"サイトマップのファイルが {MAX_FILES} を超えました")
        body = await fetcher.fetch(url)
        if body[:2] == b"\x1f\x8b":  # .gz。展開した後の大きさにも上限を置く
            body = gzip.GzipFile(fileobj=io.BytesIO(body)).read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError(f"サイトマップが大きすぎます: {url}")
        root = ElementTree.fromstring(body)
        locs = [el.text.strip() for el in root.iter() if _name(el.tag) == "loc" and el.text]
        if _name(root.tag) == "sitemapindex":
            queue.extend(locs)  # 中のサイトマップ
        elif _name(root.tag) == "urlset":
            paths.update(page_path(loc) for loc in locs)
        if len(paths) > MAX_URLS:
            raise ValueError(f"サイトマップの URL が {MAX_URLS} を超えました")
    return paths


# 手元（GLANCE_FAKE_GOOGLE=1）とテストで使うダミー。索引→2つのサイトマップの形にし、
# 検索に出ているページ（fake.py の Search Console のページ）と、出ていないページを混ぜる
FAKE_PAGES = ["/", "/glossary/wms/", "/news/2024-problem/", "/tools/%E5%80%89%E5%BA%AB/", "/glossary/amr/", "/case/picking/"]


class FakeSitemapFetcher:
    async def fetch(self, url: str) -> bytes:
        base = url.rsplit("/", 1)[0]
        ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
        if url.endswith("sitemap_index.xml"):
            items = "".join(f"<sitemap><loc>{base}/{name}</loc></sitemap>" for name in ("page-sitemap.xml", "post-sitemap.xml"))
            return f'<?xml version="1.0"?><sitemapindex {ns}>{items}</sitemapindex>'.encode()
        pages = FAKE_PAGES[:3] if url.endswith("page-sitemap.xml") else FAKE_PAGES[3:]
        items = "".join(f"<url><loc>{base}{path}</loc></url>" for path in pages)
        return f'<?xml version="1.0"?><urlset {ns}>{items}</urlset>'.encode()

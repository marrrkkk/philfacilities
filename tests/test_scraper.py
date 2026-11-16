"""Tests for the public-source crawler and extraction toolkit."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from philfacilities_ingest.scraper import (
    AsyncFetcher,
    CrawlPolicy,
    crawl,
    extract_links,
    extract_sitemap_urls,
    extract_tables,
)


def _policy(**overrides) -> CrawlPolicy:
    values = {
        "max_concurrency": 4,
        "per_host_concurrency": 2,
        "requests_per_second_per_host": 0,
        "max_pages": 10,
        "max_depth": 1,
        "retries": 1,
    }
    values.update(overrides)
    return CrawlPolicy(**values)


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_extract_links_resolves_base_and_urls() -> None:
    html = """
    <html><head><base href="/section/"></head><body>
      <a href="page.html">Page</a>
      <a href="https://example.org/absolute">Absolute</a>
      <a href="mailto:test@example.org">Mail</a>
    </body></html>
    """
    links = extract_links(html, "https://example.org/root/")
    assert "https://example.org/section/page.html" in links
    assert "https://example.org/absolute" in links
    assert "mailto:test@example.org" in links


def test_extract_tables_returns_rows() -> None:
    html = """
    <table>
      <tr><th>Name</th><th>Address</th></tr>
      <tr><td>Health Center</td><td>Barangay 1</td></tr>
    </table>
    <table><tr><td>single</td></tr></table>
    """
    tables = extract_tables(html)
    assert tables[0] == [["Name", "Address"], ["Health Center", "Barangay 1"]]
    assert tables[1] == [["single"]]


def test_extract_sitemap_urls() -> None:
    xml = "<urlset><url><loc>https://example.org/a</loc></url><url><loc>/b</loc></url></urlset>"
    assert extract_sitemap_urls(xml) == ["https://example.org/a", "/b"]


def test_crawl_discovers_same_host_pages_and_records_blocks(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if path == "/":
            return httpx.Response(
                200,
                text=(
                    "<html><body>"
                    '<a href="/a">A</a><a href="/b">B</a>'
                    '<a href="https://other.example/x">Other</a>'
                    "<table><tr><th>Name</th></tr><tr><td>A</td></tr></table>"
                    "</body></html>"
                ),
                headers={"content-type": "text/html"},
            )
        if path == "/a":
            return httpx.Response(200, text="<html>A</html>", headers={"content-type": "text/html"})
        if path == "/b":
            return httpx.Response(
                403, text="<html>Access denied</html>", headers={"content-type": "text/html"}
            )
        return httpx.Response(404)

    output = tmp_path / "crawl.jsonl"
    tables = tmp_path / "tables"
    summary = asyncio.run(
        crawl(
            ["https://example.org/"],
            policy=_policy(),
            output_path=output,
            tables_dir=tables,
            transport=_transport(handler),
        )
    )
    assert summary.pages_requested == 3
    assert summary.pages_fetched == 2
    assert summary.pages_blocked == 1
    assert summary.links_discovered == 3
    assert summary.tables_written == 1
    assert output.exists()
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert {row["url"] for row in rows} == {
        "https://example.org/",
        "https://example.org/a",
        "https://example.org/b",
    }
    assert (tables / "page-0001-table-01.csv").read_text().strip().startswith("Name")
    assert "https://other.example/x" not in {row["url"] for row in rows}


def test_crawl_honours_robots_disallow() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, text="<html>private</html>")

    summary = asyncio.run(
        crawl(
            ["https://example.org/private"],
            policy=_policy(),
            transport=_transport(handler),
        )
    )
    assert summary.pages_requested == 1
    assert summary.pages_blocked == 1
    page = summary.pages[0]
    assert page.status_code == 0
    assert page.error == "blocked_by_robots_txt"


def test_crawl_detects_challenge_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(
            200,
            text="<html><body>Just a moment... cf-chl- verify you are human</body></html>",
            headers={"content-type": "text/html"},
        )

    summary = asyncio.run(
        crawl(["https://example.org/"], policy=_policy(), transport=_transport(handler))
    )
    assert summary.pages_blocked == 1
    assert summary.pages[0].blocked is True


def test_fetch_enforces_max_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 500)

    async def run() -> None:
        async with AsyncFetcher(_policy(max_bytes=100), transport=_transport(handler)) as fetcher:
            result = await fetcher.fetch("https://example.org/large")
            assert result.status_code == 0
            assert result.error is not None
            assert "crawl limit" in result.error

    asyncio.run(run())


def test_fetch_does_not_retry_access_blocked() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(403, text="Access denied")

    async def run() -> None:
        async with AsyncFetcher(
            _policy(retries=3, respect_robots=False), transport=_transport(handler)
        ) as fetcher:
            result = await fetcher.fetch("https://example.org/blocked")
            assert result.status_code == 403

    asyncio.run(run())
    assert calls["count"] == 1

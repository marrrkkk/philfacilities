"""Polite, high-throughput acquisition toolkit for public source pages.

The toolkit exists to make repeated acquisition of *publicly accessible* official
sources fast and cheap. It provides:

* asynchronous, connection-pooled fetching with bounded global and per-host
  concurrency;
* per-host request pacing, so a crawl never turns into a burst;
* ``robots.txt`` checks (on by default);
* conditional requests (ETag / Last-Modified) and content checksums;
* retries only for transient transport errors and retryable HTTP statuses;
* hard response-size and page/depth limits;
* link discovery and HTML table extraction for directory pages;
* explicit detection of Cloudflare/WAF/CAPTCHA/login interstitials.

It never solves or bypasses a challenge, CAPTCHA, login, paywall, licence gate or
other access control. A challenge response is recorded as ``access_blocked`` and
left for an operator. The crawler also identifies itself with a real contact
route rather than impersonating a browser.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import re
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .acquisition import FetchResult, is_blocker_page, user_agent
from .config import IngestSettings

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_EXCLUDED_EXTENSIONS = (
    ".7z",
    ".avi",
    ".bmp",
    ".doc",
    ".docx",
    ".eot",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".otf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".tar",
    ".tif",
    ".tiff",
    ".ttf",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
)
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
SITEMAP_CONTENT_TYPES = ("application/xml", "text/xml")


@dataclass(frozen=True)
class CrawlPolicy:
    """Limits and politeness settings for one crawl."""

    max_concurrency: int = 8
    per_host_concurrency: int = 2
    requests_per_second_per_host: float = 1.5
    timeout_seconds: float = 30.0
    max_bytes: int = 10 * 1024 * 1024
    max_pages: int = 100
    max_depth: int = 2
    retries: int = 3
    same_host: bool = True
    respect_robots: bool = True
    include_pattern: str | None = None
    exclude_pattern: str | None = None
    excluded_extensions: tuple[str, ...] = DEFAULT_EXCLUDED_EXTENSIONS
    user_agent: str | None = None


@dataclass
class CrawlPage:
    url: str
    final_url: str
    depth: int
    status_code: int
    content_type: str | None
    sha256: str
    size_bytes: int
    elapsed_ms: int
    blocked: bool
    error: str | None = None
    links: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "depth": self.depth,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "elapsed_ms": self.elapsed_ms,
            "blocked": self.blocked,
            "error": self.error,
            "links": self.links,
        }


@dataclass
class CrawlSummary:
    started_at: str
    finished_at: str
    seed_urls: list[str]
    pages_requested: int
    pages_fetched: int
    pages_blocked: int
    pages_failed: int
    links_discovered: int
    tables_written: int
    output_path: str | None
    pages: list[CrawlPage]

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "seed_urls": self.seed_urls,
            "pages_requested": self.pages_requested,
            "pages_fetched": self.pages_fetched,
            "pages_blocked": self.pages_blocked,
            "pages_failed": self.pages_failed,
            "links_discovered": self.links_discovered,
            "tables_written": self.tables_written,
            "output_path": self.output_path,
            "pages": [page.as_dict() for page in self.pages],
        }


class AsyncFetcher:
    """Async HTTP client with bounded concurrency and per-host pacing."""

    def __init__(
        self,
        policy: CrawlPolicy | None = None,
        *,
        settings: IngestSettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.policy = policy or CrawlPolicy()
        self.settings = settings or IngestSettings()
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.policy.timeout_seconds,
            headers={
                "User-Agent": self.policy.user_agent or user_agent(self.settings),
                "Accept": "*/*",
                "Accept-Language": "en-PH,en;q=0.8",
            },
            limits=httpx.Limits(
                max_connections=max(self.policy.max_concurrency, 1),
                max_keepalive_connections=max(self.policy.per_host_concurrency, 1),
            ),
            transport=transport,
        )
        self._host_semaphores: dict[str, asyncio.Semaphore] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._next_request_at: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self) -> AsyncFetcher:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    def _semaphore(self, host: str) -> asyncio.Semaphore:
        if host not in self._host_semaphores:
            self._host_semaphores[host] = asyncio.Semaphore(self.policy.per_host_concurrency)
        return self._host_semaphores[host]

    def _lock(self, host: str) -> asyncio.Lock:
        if host not in self._host_locks:
            self._host_locks[host] = asyncio.Lock()
        return self._host_locks[host]

    async def _pace(self, host: str) -> None:
        if self.policy.requests_per_second_per_host <= 0:
            return
        interval = 1.0 / self.policy.requests_per_second_per_host
        async with self._lock(host):
            now = time.monotonic()
            wait = self._next_request_at.get(host, now) - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_request_at[host] = time.monotonic() + interval

    async def _robots_parser(self, url: str) -> RobotFileParser | None:
        if not self.policy.respect_robots:
            return None
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host in self._robots:
            return self._robots[host]
        lock = self._robots_locks.setdefault(host, asyncio.Lock())
        async with lock:
            if host in self._robots:
                return self._robots[host]
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            parser: RobotFileParser | None = None
            try:
                response = await self._client.get(
                    robots_url, timeout=min(self.policy.timeout_seconds, 10)
                )
                if response.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
                elif response.status_code in (401, 403):
                    # A protected robots.txt is treated conservatively as no access.
                    parser = RobotFileParser()
                    parser.disallow_all = True
            except httpx.HTTPError:
                parser = None
            self._robots[host] = parser
            return parser

    async def allowed(self, url: str) -> bool:
        parser = await self._robots_parser(url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.policy.user_agent or user_agent(self.settings), url)
        except Exception:
            return True

    async def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not await self.allowed(url):
            return FetchResult(
                url=url,
                final_url=url,
                status_code=0,
                content=b"",
                error="blocked_by_robots_txt",
            )

        last_error: Exception | None = None
        for attempt in range(1, self.policy.retries + 1):
            async with self._semaphore(host):
                await self._pace(host)
                started = time.monotonic()
                try:
                    result = await self._fetch_once(url, headers=headers)
                except httpx.HTTPError as exc:
                    last_error = exc
                    if attempt < self.policy.retries:
                        await asyncio.sleep(min(2**attempt, 8))
                        continue
                    return FetchResult(
                        url=url,
                        final_url=url,
                        status_code=0,
                        content=b"",
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        error=str(exc),
                    )
            if result.status_code in RETRYABLE_STATUS and attempt < self.policy.retries:
                wait = result.retry_after_seconds or min(2**attempt, 8)
                await asyncio.sleep(min(wait, 30))
                continue
            return result
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            content=b"",
            error=str(last_error) if last_error else "fetch_failed",
        )

    async def _fetch_once(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        started = time.monotonic()
        request_headers = dict(headers or {})
        async with self._client.stream("GET", url, headers=request_headers) as response:
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self.policy.max_bytes:
                    raise httpx.ReadError(
                        f"response exceeded the {self.policy.max_bytes} byte crawl limit"
                    )
                chunks.append(chunk)
            content = b"".join(chunks)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return FetchResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content=content,
                headers={key.lower(): value for key, value in response.headers.items()},
                sha256=hashlib.sha256(content).hexdigest() if content else "",
                elapsed_ms=elapsed_ms,
                not_modified=response.status_code == 304,
                retry_after_seconds=_retry_after(response.headers.get("retry-after")),
            )


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.base_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs}
        if tag.lower() == "base" and values.get("href"):
            self.base_href = values["href"]
        elif tag.lower() == "a" and values.get("href"):
            self.links.append(values["href"])


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", " ".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def extract_links(html: str, base_url: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(html)
    base = urljoin(base_url, parser.base_href) if parser.base_href else base_url
    return [urljoin(base, link) for link in parser.links]


def extract_tables(html: str) -> list[list[list[str]]]:
    parser = _TableParser()
    parser.feed(html)
    return parser.tables


def extract_sitemap_urls(xml: str) -> list[str]:
    return [match.strip() for match in re.findall(r"<loc[^>]*>(.*?)</loc>", xml, re.I | re.S)]


def _is_html(content_type: str | None, url: str) -> bool:
    lowered = (content_type or "").lower()
    if any(value in lowered for value in HTML_CONTENT_TYPES):
        return True
    return url.lower().endswith((".html", ".htm", "/"))


def _is_xml(content_type: str | None, url: str) -> bool:
    lowered = (content_type or "").lower()
    return any(value in lowered for value in SITEMAP_CONTENT_TYPES) or url.lower().endswith(
        (".xml", ".xml.gz")
    )


def _blocked(result: FetchResult) -> bool:
    return bool(result.error) or result.status_code in (401, 403) or is_blocker_page(result)


def _normalise_candidate(url: str, base_host: str, policy: CrawlPolicy) -> str | None:
    clean, _fragment = urldefrag(url.strip())
    parsed = urlparse(clean)
    if parsed.scheme not in ("http", "https"):
        return None
    if policy.same_host and parsed.netloc.lower() != base_host:
        return None
    path = parsed.path.lower()
    if any(path.endswith(extension) for extension in policy.excluded_extensions):
        return None
    if policy.include_pattern and not re.search(policy.include_pattern, clean):
        return None
    if policy.exclude_pattern and re.search(policy.exclude_pattern, clean):
        return None
    return clean


async def crawl(
    seed_urls: Iterable[str],
    *,
    policy: CrawlPolicy | None = None,
    output_path: str | Path | None = None,
    tables_dir: str | Path | None = None,
    settings: IngestSettings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CrawlSummary:
    """Crawl public pages breadth-first and optionally write JSONL/CSV artifacts."""

    policy = policy or CrawlPolicy()
    seeds = [str(url) for url in seed_urls]
    if not seeds:
        raise ValueError("At least one seed URL is required.")
    for seed in seeds:
        if urlparse(seed).scheme not in ("http", "https"):
            raise ValueError(f"Seed URL must be absolute http(s): {seed!r}")

    started_at = datetime.now(UTC).isoformat()
    pages: list[CrawlPage] = []
    requested = 0
    discovered: set[str] = set(seeds)
    tables_written = 0
    table_root = Path(tables_dir) if tables_dir else None
    if table_root is not None:
        table_root.mkdir(parents=True, exist_ok=True)

    async with AsyncFetcher(policy, settings=settings, transport=transport) as fetcher:
        queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)
        while queue and requested < policy.max_pages:
            url, depth = queue.popleft()
            requested += 1
            result = await fetcher.fetch(url)
            blocked = _blocked(result)
            links: list[str] = []
            if not blocked and result.status_code < 400:
                if _is_html(result.content_type, result.final_url):
                    html = result.content.decode("utf-8", errors="replace")
                    links = extract_links(html, result.final_url)
                    if table_root is not None:
                        tables_written += _write_tables(
                            extract_tables(html), table_root, request_index=requested
                        )
                elif _is_xml(result.content_type, result.final_url):
                    xml = result.content.decode("utf-8", errors="replace")
                    links = extract_sitemap_urls(xml)
                links = [
                    candidate
                    for link in links
                    if (
                        candidate := _normalise_candidate(
                            link, urlparse(url).netloc.lower(), policy
                        )
                    )
                ]
                for link in links:
                    if link not in discovered:
                        discovered.add(link)
                        if depth + 1 <= policy.max_depth:
                            queue.append((link, depth + 1))
            page = CrawlPage(
                url=url,
                final_url=result.final_url,
                depth=depth,
                status_code=result.status_code,
                content_type=result.content_type,
                sha256=result.sha256,
                size_bytes=len(result.content),
                elapsed_ms=result.elapsed_ms,
                blocked=blocked,
                error=result.error,
                links=links,
            )
            pages.append(page)

    finished_at = datetime.now(UTC).isoformat()
    summary = CrawlSummary(
        started_at=started_at,
        finished_at=finished_at,
        seed_urls=seeds,
        pages_requested=requested,
        pages_fetched=sum(1 for page in pages if page.status_code and page.status_code < 400),
        pages_blocked=sum(1 for page in pages if page.blocked),
        pages_failed=sum(
            1 for page in pages if not page.blocked and (page.status_code >= 400 or page.error)
        ),
        links_discovered=len(discovered),
        tables_written=tables_written,
        output_path=str(output_path) if output_path else None,
        pages=pages,
    )
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            for page in pages:
                handle.write(json.dumps(page.as_dict(), ensure_ascii=False) + "\n")
        summary.output_path = str(target)
    return summary


def _write_tables(tables: list[list[list[str]]], root: Path, *, request_index: int) -> int:
    written = 0
    for index, table in enumerate(tables, start=1):
        if len(table) < 2:
            continue
        target = root / f"page-{request_index:04d}-table-{index:02d}.csv"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(table)
        written += 1
    return written


def summary_json(summary: CrawlSummary) -> str:
    return json.dumps(summary.as_dict(), indent=2, ensure_ascii=False)

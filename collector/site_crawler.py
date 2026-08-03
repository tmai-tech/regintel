"""
Full-site BFS document crawler (based on Extraction_Script.py patterns).

Strategy (same as the colleague reference script):
1. Plain HTTP GET first (fast).
2. If the page looks like a JS shell / has almost no links, re-fetch with
   headless Chromium (Playwright) and parse the rendered HTML.
3. BFS same-site pages up to max_pages; collect every document URL
   (.pdf, optional office formats).
4. Progress is flushable; never loses the set of found URLs on crash.

This module only *discovers* document URLs. Downloading is left to the
caller (download_gazette_pdfs.py).
"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".csv", ".xls", ".xlsx")
PDF_EXTENSIONS = (".pdf",)
SKIP_HREF_PREFIX = ("javascript:", "mailto:", "tel:", "#", "data:", "blob:")
SPA_MARKERS = ('id="root"', 'id="app"', 'id="__next"', "ng-version", 'id="__nuxt"')

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class FoundDoc:
    url: str
    text: str = ""
    source_page: str = ""
    is_pdf: bool = True


@dataclass
class CrawlResult:
    start_url: str
    pages_visited: int = 0
    js_pages: int = 0
    docs: list[FoundDoc] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    empty_streak_warning: bool = False


def base_domain(netloc: str) -> str:
    return (netloc or "").lower().removeprefix("www.")


def is_same_site(netloc: str, seed_domain: str) -> bool:
    """True if netloc is the seed host or a subdomain of it.

    Only allow child hosts of the seed (e.g. docs.example.gov under example.gov).
    Do NOT treat sibling hosts under a shared public suffix as same-site
    (e.g. other.gov.sa is NOT the same site as momah.gov.sa).
    """
    a, b = base_domain(netloc), base_domain(seed_domain)
    if not a or not b:
        return False
    if a == b:
        return True
    # link host is subdomain of seed
    if a.endswith("." + b):
        return True
    return False


def has_doc_extension(url: str, extensions: tuple[str, ...] = DOC_EXTENSIONS) -> bool:
    path = urlparse(url).path.lower()
    # strip trailing junk like ;jsessionid=
    path = path.split(";")[0]
    return any(path.endswith(ext) for ext in extensions)


def looks_like_empty_shell(html: str) -> bool:
    if not html:
        return True
    lowered = html.lower()
    if len(html) < 1500:
        return True
    if any(m in lowered for m in SPA_MARKERS) and "<a " not in lowered and "<a\n" not in lowered:
        return True
    # Almost no anchors relative to size
    anchor_count = lowered.count("<a ")
    if len(html) > 8000 and anchor_count < 3:
        return True
    return False


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url.strip())
    return url


class PlaywrightRenderer:
    """Lazily launches headless Chromium only when needed (colleague pattern)."""

    def __init__(self, user_agent: str = DEFAULT_UA):
        self.user_agent = user_agent
        self._playwright = None
        self._browser = None

    @staticmethod
    def available() -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def _ensure(self) -> None:
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)

    def render(self, url: str, *, wait_ms: int = 2000, timeout_ms: int = 45000) -> tuple[str, str]:
        self._ensure()
        assert self._browser is not None
        page = self._browser.new_page(user_agent=self.user_agent)
        try:
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            page.wait_for_timeout(wait_ms)
            html = page.content()
            final = page.url
            return html, final
        finally:
            page.close()

    def close(self) -> None:
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._playwright = None


class SiteCrawler:
    """
    BFS same-site crawler that discovers document links.

    Mirrors Extraction_Script.py:
      queue → GET → optional Playwright → parse anchors → enqueue same-site / collect docs
    """

    def __init__(
        self,
        *,
        max_pages: int = 500,
        delay: float = 0.4,
        timeout: float = 20.0,
        min_links_before_fallback: int = 3,
        pdf_only: bool = True,
        use_playwright: bool = True,
        same_site_only: bool = True,
        log: Callable[[str], None] | None = None,
        extra_seed_paths: list[str] | None = None,
        regulatory_focus: bool = False,
    ):
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.min_links_before_fallback = min_links_before_fallback
        self.extensions = PDF_EXTENSIONS if pdf_only else DOC_EXTENSIONS
        self.use_playwright = use_playwright and PlaywrightRenderer.available()
        self.same_site_only = same_site_only
        self.log = log or (lambda msg: print(msg, flush=True))
        self.extra_seed_paths = extra_seed_paths or []
        # Prefer laws/regulations paths; skip news/media/careers BFS branches
        self.regulatory_focus = regulatory_focus

        self._session = None
        self._renderer: PlaywrightRenderer | None = None

    def _http_get(self, url: str) -> tuple[int | None, str, str | None, str | None]:
        """Return status, final_url, html_or_none, error."""
        try:
            import httpx
        except ImportError:
            import requests

            try:
                r = requests.get(
                    url,
                    timeout=self.timeout,
                    headers={"User-Agent": DEFAULT_UA, "Accept": "text/html,*/*"},
                    allow_redirects=True,
                )
                ct = r.headers.get("Content-Type", "")
                if r.status_code == 200 and (
                    "text/html" in ct or "application/xhtml" in ct or not ct or "text/" in ct
                ):
                    # if body is PDF bytes, skip
                    if r.content[:4] == b"%PDF":
                        return r.status_code, r.url, None, "direct-pdf"
                    return r.status_code, r.url, r.text, None
                if r.status_code == 200 and "pdf" in ct.lower():
                    return r.status_code, r.url, None, "direct-pdf"
                return r.status_code, r.url, None, f"HTTP {r.status_code} ct={ct}"
            except Exception as e:
                return None, url, None, str(e)[:240]

        if self._session is None:
            self._session = httpx.Client(
                timeout=httpx.Timeout(self.timeout, connect=12.0),
                headers={
                    "User-Agent": DEFAULT_UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
                http2=False,
            )
        try:
            r = self._session.get(url)
            ct = r.headers.get("content-type", "")
            final = str(r.url)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                return r.status_code, final, None, "direct-pdf"
            if r.status_code == 200 and (
                "text/html" in ct
                or "application/xhtml" in ct
                or "text/plain" in ct
                or "xml" in ct
                or not ct
            ):
                return r.status_code, final, r.text, None
            if r.status_code == 200 and "pdf" in ct.lower():
                return r.status_code, final, None, "direct-pdf"
            return r.status_code, final, None, f"HTTP {r.status_code} ct={ct}"
        except Exception as e:
            return None, url, None, str(e)[:240]

    def _render(self, url: str) -> tuple[str | None, str, str | None]:
        if not self.use_playwright:
            return None, url, "playwright disabled/unavailable"
        if self._renderer is None:
            self._renderer = PlaywrightRenderer()
        try:
            html, final = self._renderer.render(url)
            return html, final, None
        except Exception as e:
            return None, url, str(e)[:240]

    def _extract_anchors(self, base_url: str, html: str) -> list[tuple[str, str]]:
        """Return list of (absolute_url, link_text)."""
        soup = BeautifulSoup(html, "lxml")
        out: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(href: str | None, text: str = ""):
            if not href:
                return
            href = href.strip()
            if not href or href.lower().startswith(SKIP_HREF_PREFIX):
                return
            full = normalize_url(urljoin(base_url, href))
            parsed = urlparse(full)
            if parsed.scheme not in ("http", "https"):
                return
            if full in seen:
                return
            seen.add(full)
            out.append((full, " ".join((text or "").split())[:300]))

        for a in soup.find_all("a", href=True):
            add(a.get("href"), a.get_text(" ", strip=True))
        for tag in soup.find_all(["iframe", "embed", "object", "source"]):
            for attr in ("src", "data", "data-src", "href"):
                if tag.get(attr):
                    add(tag.get(attr), tag.get("title") or "")
        for el in soup.find_all(attrs={"data-url": True}):
            add(el.get("data-url"), el.get_text(" ", strip=True))
        for el in soup.find_all(attrs={"data-href": True}):
            add(el.get("data-href"), el.get_text(" ", strip=True))
        # bare document URLs in HTML (SPAs / JSON blobs)
        for m in re.finditer(
            r"""https?://[^\s"'<>]+?\.(?:pdf|docx?|xlsx?|csv)(?:\?[^\s"'<>]*)?""",
            html,
            re.I,
        ):
            add(m.group(0), "embedded-url")
        # relative .pdf paths
        for m in re.finditer(
            r"""["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
            html,
            re.I,
        ):
            add(m.group(1), "quoted-path")

        return out

    def crawl(self, start_url: str) -> CrawlResult:
        start_url = normalize_url(start_url)
        if not start_url.startswith("http"):
            start_url = "https://" + start_url.lstrip("/")

        seed = urlparse(start_url)
        result = CrawlResult(start_url=start_url)
        visited: set[str] = set()
        docs_seen: set[str] = set()
        # priority queue: legal paths first (0), normal (1), low (2)
        queue: deque[tuple[int, str]] = deque([(0, start_url)])

        # optional extra paths under same host (listing shortcuts)
        for path in self.extra_seed_paths:
            if path.startswith("http"):
                queue.append((0, normalize_url(path)))
            else:
                queue.append((0, normalize_url(urljoin(start_url, path))))

        consecutive_empty = 0

        def _enqueue(full: str, prio: int = 1) -> None:
            if full in visited:
                return
            if self.regulatory_focus:
                try:
                    from collector.pdf_relevance import is_junk_page, is_legal_priority_page
                except ImportError:
                    from pdf_relevance import is_junk_page, is_legal_priority_page  # type: ignore
                if is_junk_page(full):
                    return
                if is_legal_priority_page(full):
                    prio = 0
            # insert by priority (simple: left for high, right for low)
            if prio <= 0:
                queue.appendleft((prio, full))
            else:
                queue.append((prio, full))

        try:
            while queue and len(visited) < self.max_pages:
                # always take highest priority currently at left; re-sort lightly
                # (appendleft for prio 0 keeps legal pages ahead of bulk)
                _prio, url = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)
                time.sleep(self.delay)

                # If the queue item itself is a document, record it
                if has_doc_extension(url, self.extensions):
                    if url not in docs_seen:
                        docs_seen.add(url)
                        result.docs.append(
                            FoundDoc(
                                url=url,
                                text="",
                                source_page=start_url,
                                is_pdf=urlparse(url).path.lower().endswith(".pdf"),
                            )
                        )
                        self.log(f"    -> DOC FOUND: {url}")
                    continue

                status, final_url, html, err = self._http_get(url)
                used_js = False

                # Colleague pattern: fallback when missing HTML or empty SPA shell
                needs_fallback = (
                    html is None
                    or looks_like_empty_shell(html)
                    or (
                        html is not None
                        and html.lower().count("<a ") < self.min_links_before_fallback
                    )
                )
                # always try playwright on hard errors / 403 if enabled
                if err and status in (401, 403, 429, None) and self.use_playwright:
                    needs_fallback = True
                if err == "direct-pdf":
                    if final_url not in docs_seen:
                        docs_seen.add(final_url)
                        result.docs.append(
                            FoundDoc(url=final_url, source_page=url, is_pdf=True)
                        )
                        self.log(f"    -> DOC FOUND (direct): {final_url}")
                    continue

                if needs_fallback and self.use_playwright:
                    html2, final2, err2 = self._render(url)
                    if html2:
                        html, final_url = html2, final2
                        used_js = True
                        result.js_pages += 1
                    elif html is None:
                        msg = f"[{len(visited)}] ERROR {url} -> {err or err2}"
                        result.errors.append(msg)
                        self.log(msg)
                        continue

                if html is None:
                    msg = f"[{len(visited)}] SKIP {url} -> {err or 'no html'}"
                    result.errors.append(msg)
                    self.log(msg)
                    continue

                tag = "JS " if used_js else "   "
                self.log(f"[{len(visited)}] {tag}{url}")

                anchors = self._extract_anchors(final_url, html)
                if not anchors:
                    consecutive_empty += 1
                    self.log(
                        "    (no links found — may need login, or API content "
                        "Playwright wait did not catch)"
                    )
                    if consecutive_empty >= 8:
                        result.empty_streak_warning = True
                        self.log(
                            "!! WARNING: 8+ pages with zero links — possible "
                            "rate-limit/block. Consider higher delay or proxy."
                        )
                else:
                    consecutive_empty = 0

                for full, text in anchors:
                    if has_doc_extension(full, self.extensions):
                        if full not in docs_seen:
                            docs_seen.add(full)
                            result.docs.append(
                                FoundDoc(
                                    url=full,
                                    text=text,
                                    source_page=url,
                                    is_pdf=urlparse(full).path.lower().split(";")[0].endswith(".pdf"),
                                )
                            )
                            self.log(f"    -> DOC FOUND: {full}")
                        continue

                    # Enqueue same-site HTML pages for BFS
                    host = urlparse(full).netloc
                    if self.same_site_only and not is_same_site(host, seed.netloc):
                        continue
                    # skip binary-ish query downloads without extension handled above
                    if full not in visited:
                        _enqueue(full, prio=1)

            result.pages_visited = len(visited)
            self.log(
                f"Crawl done: {result.pages_visited} pages, "
                f"{result.js_pages} JS-rendered, {len(result.docs)} documents"
            )
            return result
        finally:
            if self._renderer:
                self._renderer.close()
                self._renderer = None
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    pass
                self._session = None

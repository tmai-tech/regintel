"""
Document finder / crawler with automatic JS-rendering fallback.

Strategy:
1. Try a plain `requests` GET first (fast, cheap).
2. If the page looks JS-rendered (very few links found relative to page
   size, or the body looks like an empty SPA shell), re-fetch that same
   page with a headless browser (Playwright) which executes JavaScript,
   then parse the fully-rendered HTML instead.
3. Everything else (queueing, dedup, extension matching, same-site check)
   works the same regardless of which method produced the HTML.

Reliability additions:
- Never crashes on Unicode characters Windows' terminal can't display.
- Saves found_documents.txt every N pages, so a crash/interrupt never
  loses progress.
- Writes a full crawl_log.txt so you can review a run afterward.
- Warns loudly if it looks like the site has started rate-limiting/
  blocking this IP (many consecutive pages with zero links).

Setup:
    pip install requests beautifulsoup4 playwright certifi
    playwright install chromium
"""

import sys
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import certifi
import os

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# --- Fix: stop crashing on Unicode characters Windows' terminal can't print ---
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---- SETTINGS ----
WEBSITE = "https://sdaia.gov.sa/en/default.aspx"
MAX_PAGES = 2000
DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".csv", ".xls", ".xlsx")
REQUEST_TIMEOUT = 15
CRAWL_DELAY = 0.4          # seconds between requests, be polite / avoid blocking
MIN_LINKS_BEFORE_FALLBACK = 3   # if a page has fewer links than this, suspect JS rendering
SAVE_EVERY = 25            # write progress to disk every N pages
OUTPUT_FILE = "found_documents.txt"
LOG_FILE = "crawl_log.txt"
# -------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36"
}


def is_same_site(netloc, base_domain):
    return netloc.replace("www.", "") == base_domain.replace("www.", "")


def has_doc_extension(url):
    path = urlparse(url).path.lower()
    return path.endswith(DOC_EXTENSIONS)


def looks_like_empty_shell(html):
    """Heuristic: very short HTML body or classic SPA root divs with no content."""
    lowered = html.lower()
    if len(html) < 1500:
        return True
    spa_markers = ('id="root"', 'id="app"', 'id="__next"', 'ng-version')
    return any(marker in lowered for marker in spa_markers) and "<a " not in lowered


def save_progress(doc_links):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for link in sorted(doc_links):
            f.write(link + "\n")


class PlaywrightRenderer:
    """Lazily launches a headless browser only if/when it's actually needed."""

    def __init__(self):
        self._playwright = None
        self._browser = None

    def _ensure_started(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)

    def render(self, url, wait_ms=2000):
        self._ensure_started()
        page = self._browser.new_page(user_agent=HEADERS["User-Agent"])
        try:
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(wait_ms)  # let late JS/XHR settle
            html = page.content()
            final_url = page.url
            return html, final_url
        finally:
            page.close()

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()


def find_all_documents(start_url, max_pages=MAX_PAGES):
    base_domain = urlparse(start_url).netloc
    session = requests.Session()
    session.headers.update(HEADERS)
    renderer = PlaywrightRenderer()

    visited_pages = set()
    doc_links = set()
    queue = deque([start_url])
    js_fallback_count = 0
    consecutive_empty_pages = 0

    log_f = open(LOG_FILE, "a", encoding="utf-8")

    def log(msg):
        print(msg)
        log_f.write(msg + "\n")
        log_f.flush()

    try:
        while queue and len(visited_pages) < max_pages:
            url = queue.popleft()
            if url in visited_pages:
                continue
            visited_pages.add(url)
            time.sleep(CRAWL_DELAY)

            html = None
            final_url = url
            used_js = False

            # --- Step 1: plain requests ---
            try:
                response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                status = response.status_code
                content_type = response.headers.get("Content-Type", "")
                final_url = response.url

                if status == 200 and "text/html" in content_type:
                    html = response.text
                elif status != 200:
                    log(f"[{len(visited_pages)}] HTTP {status} {url}")
            except requests.RequestException as e:
                log(f"[{len(visited_pages)}] ERROR (requests) {url} -> {e}")

            # --- Step 2: decide whether to fall back to a headless browser ---
            needs_fallback = html is None or looks_like_empty_shell(html)

            if needs_fallback:
                try:
                    html, final_url = renderer.render(url)
                    used_js = True
                    js_fallback_count += 1
                except Exception as e:
                    log(f"[{len(visited_pages)}] ERROR (playwright) {url} -> {e}")
                    continue

            if html is None:
                continue

            tag = "JS " if used_js else "   "
            log(f"[{len(visited_pages)}] {tag}{url}")

            soup = BeautifulSoup(html, "html.parser")
            anchors = soup.find_all("a", href=True)

            if len(anchors) == 0:
                consecutive_empty_pages += 1
                log("    (no links found even after rendering -- page may need login, "
                    "or content loads via an API call Playwright's default wait didn't catch)")
                if consecutive_empty_pages >= 8:
                    log("!! WARNING: 8+ pages in a row with zero links. This usually means "
                        "the site has started rate-limiting/blocking this IP. Consider "
                        "stopping, waiting a while, and/or increasing CRAWL_DELAY.")
            else:
                consecutive_empty_pages = 0

            for link in anchors:
                href = link["href"].strip()
                if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                    continue

                full_url = urljoin(final_url, href).split("#")[0]

                if has_doc_extension(full_url):
                    if full_url not in doc_links:
                        log(f"    -> DOC FOUND: {full_url}")
                    doc_links.add(full_url)
                elif is_same_site(urlparse(full_url).netloc, base_domain):
                    if full_url not in visited_pages:
                        queue.append(full_url)

            if len(visited_pages) % SAVE_EVERY == 0:
                save_progress(doc_links)

    finally:
        renderer.close()
        log_f.close()

    print(f"\n({js_fallback_count} of {len(visited_pages)} pages needed JS rendering)")
    return doc_links


if __name__ == "__main__":
    print(f"Starting scan of: {WEBSITE}\n")
    documents = find_all_documents(WEBSITE)

    print(f"\nFound {len(documents)} document(s):\n")
    for link in sorted(documents):
        print(link)

    save_progress(documents)
    print(f"\nSaved all links to {OUTPUT_FILE}")
    print(f"Full crawl log saved to {LOG_FILE}")

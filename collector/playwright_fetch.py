"""Optional Playwright HTML fetch for JS-rendered or bot-blocked pages."""
from __future__ import annotations

from typing import Optional

_browser = None
_playwright = None


def available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_html(url: str, *, timeout_ms: int = 45000, wait_ms: int = 2000) -> tuple[Optional[int], Optional[str], Optional[bytes], Optional[str]]:
    """Return (status, content_type, body, error) using headless Chromium."""
    global _browser, _playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, None, None, "playwright not installed"

    try:
        if _playwright is None:
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=True)
        context = _browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(wait_ms)
        html = page.content()
        status = resp.status if resp else 200
        context.close()
        return status, "text/html", html.encode("utf-8", errors="replace"), None
    except Exception as e:
        return None, None, None, str(e)[:300]


def shutdown():
    global _browser, _playwright
    try:
        if _browser:
            _browser.close()
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _browser = None
    _playwright = None

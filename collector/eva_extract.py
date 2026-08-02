"""Extract plain text from local or remote PDF files for Eva."""
from __future__ import annotations

import io
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UA = (
    "Mozilla/5.0 (compatible; RegIntel-Eva/1.0; +https://github.com/tmai-tech/regintel)"
)


def extract_text_from_bytes(
    data: bytes,
    *,
    max_pages: int = 20,
    max_chars: int = 40_000,
) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is required: pip install pypdf") from e

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    n = min(len(reader.pages), max_pages)
    for i in range(n):
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception:
            t = ""
        t = t.strip()
        if t:
            parts.append(t)
        joined = "\n\n".join(parts)
        if len(joined) >= max_chars:
            return joined[:max_chars]
    text = "\n\n".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars].strip()


def extract_text_from_path(
    path: Path,
    *,
    max_pages: int = 20,
    max_chars: int = 40_000,
) -> str:
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Not a PDF: {path}")
    return extract_text_from_bytes(data, max_pages=max_pages, max_chars=max_chars)


def extract_text_from_url(
    url: str,
    *,
    timeout: float = 45.0,
    max_pages: int = 20,
    max_chars: int = 40_000,
    referer: str | None = None,
) -> str:
    headers = {"User-Agent": DEFAULT_UA, "Accept": "application/pdf,*/*"}
    if referer:
        headers["Referer"] = referer
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.content
    if not data.startswith(b"%PDF"):
        raise ValueError(f"URL did not return a PDF: {urlparse(url).netloc}")
    return extract_text_from_bytes(data, max_pages=max_pages, max_chars=max_chars)


def resolve_pdf_bytes_or_path(rec: dict) -> tuple[bytes | None, Path | None]:
    """Prefer local file under data/pdfs, else remote URL."""
    local = rec.get("local_path") or rec.get("path")
    if local:
        p = ROOT / local if not Path(local).is_absolute() else Path(local)
        if p.is_file():
            return None, p
    url = rec.get("open_url") or rec.get("url") or rec.get("download_url")
    if url and str(url).startswith("http"):
        return None, None  # signal URL path
    return None, None


def extract_for_record(
    rec: dict,
    *,
    max_pages: int = 20,
    max_chars: int = 40_000,
) -> str:
    local = rec.get("local_path") or rec.get("path")
    if local:
        p = ROOT / local if not Path(local).is_absolute() else Path(local)
        if p.is_file():
            return extract_text_from_path(p, max_pages=max_pages, max_chars=max_chars)
    url = rec.get("open_url") or rec.get("url") or ""
    if url.startswith("http"):
        return extract_text_from_url(
            url,
            max_pages=max_pages,
            max_chars=max_chars,
            referer=rec.get("source_page"),
        )
    raise FileNotFoundError("No local path or HTTP URL for PDF")

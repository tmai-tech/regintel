"""Extract plain text from local or remote PDF files for Eva."""
from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UA = (
    "Mozilla/5.0 (compatible; RegIntel-Eva/1.0; +https://github.com/tmai-tech/regintel)"
)

# pypdf dumps these when an Arabic font has no ToUnicode map.
_UNI_SLASH = re.compile(r"/uni([0-9A-Fa-f]{4,6})")
_UNI_BARE = re.compile(r"(?<![A-Za-z0-9])uni([0-9A-Fa-f]{4})(?![0-9A-Fa-f])")
_GLYPH_JUNK = re.compile(
    r"kashke(?:\.\d+)?|\.(?:narrow|wide|swash|medi|init|fina|isol)(?![A-Za-z])",
    re.IGNORECASE,
)
_ARABIC_LETTER = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


def _chr_hex(m: re.Match) -> str:
    try:
        return chr(int(m.group(1), 16))
    except ValueError:
        return ""


def decode_pdf_glyph_names(text: str) -> str:
    """Turn /uniFEF2 style glyph names into real characters."""
    text = _UNI_SLASH.sub(_chr_hex, text)
    text = _UNI_BARE.sub(_chr_hex, text)
    text = _GLYPH_JUNK.sub(" ", text)
    return unicodedata.normalize("NFKC", text)


def looks_like_glyph_dump(text: str) -> bool:
    if not text:
        return False
    blob = text.lower()
    if "/uni" in blob or "kashke" in blob:
        return True
    return bool(_UNI_BARE.search(text))


def _mostly_arabic(s: str) -> bool:
    letters = [c for c in s if c.isalpha() or _ARABIC_LETTER.search(c)]
    if len(letters) < 8:
        return False
    ar = sum(1 for c in letters if _ARABIC_LETTER.search(c))
    return ar / len(letters) >= 0.5


def _unreverse_visual_line(s: str) -> str:
    """PDF Arabic is often stored in visual order. Flip letter runs, keep digits."""
    flipped = s[::-1]

    def _restore_ltr(m: re.Match) -> str:
        return m.group(0)[::-1]

    return re.sub(r"[0-9A-Za-z][0-9A-Za-z.\-/]*", _restore_ltr, flipped)


def clean_extracted_text(text: str) -> str:
    """Decode custom-font glyph dumps and tidy extraction noise."""
    if not text:
        return ""
    out: list[str] = []
    for raw_line in text.splitlines():
        had_uni = looks_like_glyph_dump(raw_line)
        line = decode_pdf_glyph_names(raw_line)
        line = re.sub(r"\.{6,}", " ", line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        if had_uni and _mostly_arabic(line):
            line = _unreverse_visual_line(line)
        if line:
            out.append(line)
    cleaned = "\n".join(out)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


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
        joined = clean_extracted_text("\n\n".join(parts))
        if len(joined) >= max_chars:
            return joined[:max_chars]
    text = "\n\n".join(parts)
    text = clean_extracted_text(text)
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
    last_err: Exception | None = None
    data = b""
    for verify in (True, False):
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
                verify=verify,
            ) as client:
                r = client.get(url)
                r.raise_for_status()
                data = r.content
            last_err = None
            break
        except Exception as e:
            last_err = e
            if verify and (
                "CERTIFICATE" in str(e).upper()
                or "SSL" in str(e).upper()
                or "TLS" in str(e).upper()
            ):
                continue
            raise
    if last_err is not None:
        raise last_err
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

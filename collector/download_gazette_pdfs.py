#!/usr/bin/env python3
"""
Scrape Gazette & Parliament Bills links from the BCI Tracking Plan catalog
and download amendment / bill PDFs discovered on those pages.

Sources (per jurisdiction in data/gazette.json):
  - parliamentary_bills
  - official_gazette  (may contain multiple URLs separated by ';')
  - legal_databases   (optional; used when --include-legal-db)

Output:
  data/pdfs/<jurisdiction_slug>/<source_kind>/...
  data/pdfs/manifest.json   — full inventory of discovered + downloaded files
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GAZETTE_JSON = DATA / "gazette.json"
PDF_ROOT = DATA / "pdfs"
MANIFEST_PATH = PDF_ROOT / "manifest.json"

UA = (
    "BCI-RegIntel/1.0 (+https://github.com/tmai-tech/regintel; "
    "gazette-bill-pdf-collector; research)"
)

# Path/text signals that a link is likely a bill / amendment / legislative PDF
BILL_KEYWORDS = (
    "bill",
    "amendment",
    "amended",
    "amending",
    "amdt",
    "draft",
    "legislation",
    "statute",
    "act-",
    "/act/",
    "regulation",
    "ordonnance",
    "projet",
    "loi",
    "gesetz",
    "wetsvoorstel",
    "proposition",
    "si-",  # UK statutory instrument style
    "statutory",
    "order",
    "instrument",
    "gazette",
    "notice",
    "resolution",
    "decree",
    "ordinance",
    "white-paper",
    "whitepaper",
    "green-paper",
    "greenpaper",
    "reading",
    "committee",
    "report-stage",
    "royal-assent",
    "enacted",
    "public bill",
    "private bill",
    "hybrid bill",
)

PDF_EXT_RE = re.compile(r"\.pdf($|\?|#)", re.I)
SKIP_HREF_PREFIX = ("javascript:", "mailto:", "tel:", "#", "data:")

# Hosts that often block generic bots — still try, but note in log
def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text or "unknown", flags=re.U)
    s = re.sub(r"[-\s]+", "_", s.strip()).strip("_")
    return s[:80] or "unknown"


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def load_gazette() -> list[dict]:
    if not GAZETTE_JSON.exists():
        raise SystemExit(f"Missing {GAZETTE_JSON} — run scripts/seed_from_excel.py first")
    return json.loads(GAZETTE_JSON.read_text(encoding="utf-8"))


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "generated_at": None,
        "downloads": [],
        "discovered": [],
        "errors": [],
        "stats": {},
    }


def save_manifest(manifest: dict) -> None:
    PDF_ROOT.mkdir(parents=True, exist_ok=True)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def split_urls(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[;\n|]+", str(value))
    out = []
    for p in parts:
        u = p.strip()
        if not u:
            continue
        if not u.startswith("http"):
            u = "https://" + u.lstrip("/")
        out.append(u)
    return out


def looks_like_bill_or_amendment(url: str, text: str = "") -> bool:
    blob = f"{url} {text}".lower()
    if PDF_EXT_RE.search(url):
        # PDF link: accept if keyword hit OR generic legislative context
        if any(k in blob for k in BILL_KEYWORDS):
            return True
        # Many gazette sites name files like 2025-123.pdf — still want PDFs from bill/gazette pages
        return True
    return any(k in blob for k in BILL_KEYWORDS)


def is_pdf_url(url: str, content_type: str | None = None) -> bool:
    if PDF_EXT_RE.search(url or ""):
        return True
    if content_type and "pdf" in content_type.lower():
        return True
    return False


def extract_links(base_url: str, html: str) -> list[dict]:
    """Return [{url, text, is_pdf}] from page anchors + common embed sources."""
    soup = BeautifulSoup(html, "lxml")
    found: list[dict] = []
    seen: set[str] = set()

    def add(href: str, text: str = ""):
        if not href:
            return
        href = href.strip()
        if href.lower().startswith(SKIP_HREF_PREFIX):
            return
        full = urljoin(base_url, href).split("#")[0]
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            return
        if full in seen:
            return
        seen.add(full)
        text = " ".join((text or "").split())
        found.append(
            {
                "url": full,
                "text": text[:300],
                "is_pdf": bool(PDF_EXT_RE.search(full)),
            }
        )

    for a in soup.find_all("a", href=True):
        add(a["href"], a.get_text(" ", strip=True))

    for tag in soup.find_all(["iframe", "embed", "object", "source"]):
        for attr in ("src", "data", "data-src", "href"):
            if tag.get(attr):
                add(tag.get(attr), tag.get("title") or tag.get("type") or "")

    # Inline onclick / data attributes that point at PDFs
    for el in soup.find_all(attrs={"data-url": True}):
        add(el["data-url"], el.get_text(" ", strip=True))
    for el in soup.find_all(attrs={"data-href": True}):
        add(el["data-href"], el.get_text(" ", strip=True))

    # Bare .pdf strings in HTML (some SPAs)
    for m in re.finditer(r"https?://[^\s\"'<>]+\.pdf(?:\?[^\s\"'<>]*)?", html, re.I):
        add(m.group(0), "embedded-url")

    return found


def safe_filename(url: str, title: str = "") -> str:
    parsed = urlparse(url)
    name = unquote(Path(parsed.path).name or "document.pdf")
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf"
    name = re.sub(r"[^\w.\-()+ ]+", "_", name)
    name = name.strip(" ._") or "document.pdf"
    if len(name) > 140:
        stem = Path(name).stem[:100]
        name = f"{stem}_{content_hash(url.encode())}.pdf"
    # prefix short title hash if generic
    if name.lower() in ("document.pdf", "file.pdf", "download.pdf", "pdf.pdf"):
        base = slugify(title)[:40] or content_hash(url.encode())
        name = f"{base}.pdf"
    return name


class GazettePdfCollector:
    def __init__(
        self,
        *,
        max_pdfs_per_source: int = 40,
        max_follow_pages: int = 15,
        delay: float = 0.6,
        include_legal_db: bool = False,
        jurisdictions: list[str] | None = None,
        dry_run: bool = False,
        timeout: float = 30.0,
    ):
        self.max_pdfs_per_source = max_pdfs_per_source
        self.max_follow_pages = max_follow_pages
        self.delay = delay
        self.include_legal_db = include_legal_db
        self.jurisdictions = {j.lower() for j in jurisdictions} if jurisdictions else None
        self.dry_run = dry_run
        self.timeout = timeout
        self.manifest = load_manifest()
        self._downloaded_urls = {
            d.get("url") for d in self.manifest.get("downloads", []) if d.get("url")
        }
        self._file_hashes = {
            d.get("sha256") for d in self.manifest.get("downloads", []) if d.get("sha256")
        }
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=15.0),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
                    f"{UA}"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=True,
            http2=False,
        )
        self.stats = {
            "sources_visited": 0,
            "pages_fetched": 0,
            "pdfs_discovered": 0,
            "pdfs_downloaded": 0,
            "pdfs_skipped_existing": 0,
            "errors": 0,
        }

    def close(self):
        self.client.close()
        self.manifest["stats"] = self.stats
        save_manifest(self.manifest)

    def fetch(
        self,
        url: str,
        extra_headers: dict | None = None,
    ) -> tuple[int | None, str | None, bytes | None, str | None]:
        """Return (status, content_type, body, error)."""
        try:
            resp = self.client.get(url, headers=extra_headers or None)
            ct = resp.headers.get("content-type", "")
            return resp.status_code, ct, resp.content, None
        except Exception as e:
            return None, None, None, str(e)[:300]

    def download_pdf(
        self,
        *,
        url: str,
        jurisdiction: str,
        source_kind: str,
        source_page: str,
        title: str,
    ) -> dict | None:
        if url in self._downloaded_urls:
            self.stats["pdfs_skipped_existing"] += 1
            return None

        jslug = slugify(jurisdiction)
        out_dir = PDF_ROOT / jslug / source_kind
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = safe_filename(url, title)
        # avoid collision
        dest = out_dir / fname
        if dest.exists():
            dest = out_dir / f"{Path(fname).stem}_{content_hash(url.encode())}.pdf"

        if self.dry_run:
            rec = {
                "url": url,
                "jurisdiction": jurisdiction,
                "source_kind": source_kind,
                "source_page": source_page,
                "title": title,
                "path": str(dest.relative_to(ROOT)),
                "dry_run": True,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            self.manifest.setdefault("discovered", []).append(rec)
            self.stats["pdfs_discovered"] += 1
            print(f"  [dry-run] {url}")
            return rec

        headers = {}
        # Many parliamentary hosts require a browser-like Referer
        if "parliament.uk" in url or "publications.parliament.uk" in url:
            headers["Referer"] = "https://bills.parliament.uk/"
        elif source_page:
            headers["Referer"] = source_page
        status, ct, body, err = self.fetch(url, extra_headers=headers or None)
        time.sleep(self.delay)
        # Retry once on 403 with alternate referer / bare browser UA path
        if status == 403:
            headers["Referer"] = source_page or "https://www.google.com/"
            headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            status, ct, body, err = self.fetch(url, extra_headers=headers)
            time.sleep(self.delay)
        if err or not body:
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {"url": url, "error": err or "empty body", "stage": "download_pdf"}
            )
            print(f"  [fail] {url} — {err or 'empty'}")
            return None
        if status and status >= 400:
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {"url": url, "error": f"HTTP {status}", "stage": "download_pdf"}
            )
            print(f"  [http {status}] {url}")
            return None
        if not is_pdf_url(url, ct):
            # some servers omit extension / content-type; check magic
            if not body.startswith(b"%PDF"):
                self.stats["errors"] += 1
                self.manifest.setdefault("errors", []).append(
                    {
                        "url": url,
                        "error": f"not a PDF (ct={ct})",
                        "stage": "download_pdf",
                    }
                )
                print(f"  [skip not-pdf] {url} ct={ct}")
                return None

        sha = content_hash(body)
        if sha in self._file_hashes:
            self.stats["pdfs_skipped_existing"] += 1
            print(f"  [dup hash] {url}")
            return None

        dest.write_bytes(body)
        self._downloaded_urls.add(url)
        self._file_hashes.add(sha)
        rec = {
            "url": url,
            "jurisdiction": jurisdiction,
            "source_kind": source_kind,
            "source_page": source_page,
            "title": title,
            "path": str(dest.relative_to(ROOT)),
            "bytes": len(body),
            "sha256": sha,
            "http_status": status,
            "content_type": ct,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.manifest.setdefault("downloads", []).append(rec)
        self.stats["pdfs_downloaded"] += 1
        self.stats["pdfs_discovered"] += 1
        print(f"  [ok] {dest.name} ({len(body)} bytes) ← {url[:100]}")
        return rec


    def site_specific_pdfs(self, page_url: str) -> list[dict]:
        """Known APIs / endpoints that return bill or amendment document links."""
        host = urlparse(page_url).netloc.lower()
        out: list[dict] = []

        # UK Parliament Bills API
        if "bills.parliament.uk" in host or "parliament.uk" in host and "bill" in page_url.lower():
            api = "https://bills-api.parliament.uk/api/v1/Bills?Take=40&SortOrder=DateUpdatedDescending"
            st, ct, body, err = self.fetch(api)
            time.sleep(self.delay)
            if body and not err and st and st < 400:
                try:
                    data = json.loads(body.decode("utf-8", errors="replace"))
                    items = data if isinstance(data, list) else data.get("items") or data.get("results") or []
                    for it in items:
                        bid = it.get("billId") or it.get("id")
                        title = it.get("shortTitle") or it.get("title") or f"Bill {bid}"
                        if not bid:
                            continue
                        # Publications endpoint often lists PDFs
                        pub = f"https://bills-api.parliament.uk/api/v1/Bills/{bid}/Publications"
                        st2, _, body2, err2 = self.fetch(pub)
                        time.sleep(self.delay)
                        if err2 or not body2 or (st2 and st2 >= 400):
                            continue
                        try:
                            pubs = json.loads(body2.decode("utf-8", errors="replace"))
                        except Exception:
                            continue
                        if isinstance(pubs, dict):
                            pubs = pubs.get("publications") or pubs.get("items") or []
                        if isinstance(pubs, dict):
                            pub_list = pubs.get("publications") or pubs.get("items") or []
                        else:
                            pub_list = pubs or []
                        for pub_item in pub_list:
                            candidates = []
                            candidates.extend(pub_item.get("links") or [])
                            candidates.extend(pub_item.get("files") or [])
                            candidates.append(pub_item)
                            for f in candidates:
                                if not isinstance(f, dict):
                                    continue
                                url = (
                                    f.get("url")
                                    or f.get("fileUrl")
                                    or f.get("filenameUrl")
                                    or f.get("downloadUrl")
                                )
                                ctype = (f.get("contentType") or "") + " " + (f.get("title") or "")
                                if not url:
                                    continue
                                if ".pdf" in str(url).lower() or "pdf" in ctype.lower() or "application/pdf" in ctype.lower():
                                    if not str(url).startswith("http"):
                                        url = urljoin("https://publications.parliament.uk/", url)
                                    out.append({
                                        "url": url,
                                        "text": f"{title} — {pub_item.get('title') or f.get('title') or 'publication'}",
                                        "is_pdf": True,
                                    })
                except Exception as e:
                    print(f"  [uk api] {e}")

        # legislation.gov.uk recent / new legislation atom often has PDFs
        if "legislation.gov.uk" in host:
            for feed in (
                "https://www.legislation.gov.uk/new/data.feed",
                "https://www.legislation.gov.uk/uksi/data.feed",
                "https://www.legislation.gov.uk/ukpga/data.feed",
            ):
                st, _, body, err = self.fetch(feed)
                time.sleep(self.delay)
                if err or not body or (st and st >= 400):
                    continue
                html = body.decode("utf-8", errors="replace")
                for link in extract_links(feed, html):
                    # data.feed entries link to instruments; PDF usually at {id}/data.pdf or /pdfs/…
                    u = link["url"]
                    if "/id/" in u or "legislation.gov.uk" in u:
                        for suffix in ("/data.pdf", "/pdfs/contents.pdf", "/pdfs/ukpga_en.pdf"):
                            # only for document-like paths
                            if any(x in u for x in ("/ukpga/", "/uksi/", "/ukla/", "/asp/", "/anaw/", "/nia/")):
                                pdf_u = u.rstrip("/") + suffix if not u.endswith(".pdf") else u
                                # legislation.gov.uk standard: https://www.legislation.gov.uk/uksi/2025/123/data.pdf
                                if "/data.pdf" in suffix:
                                    # strip /contents etc
                                    base = u.split("?")[0].rstrip("/")
                                    # remove trailing section paths beyond year/number
                                    parts = base.split("/")
                                    # keep up to type/year/number roughly
                                    pdf_u = base + "/data.pdf"
                                out.append({"url": pdf_u, "text": link["text"] or "legislation", "is_pdf": True})
                # also direct pdfs in feed
                for link in extract_links(feed, html):
                    if link["is_pdf"]:
                        out.append(link)

        # Federal Register API (US gazette)
        if "federalregister.gov" in host:
            api = "https://www.federalregister.gov/api/v1/documents.json?per_page=20&order=newest&conditions%5Btype%5D%5B%5D=RULE&conditions%5Btype%5D%5B%5D=PRORULE&conditions%5Btype%5D%5B%5D=NOTICE"
            st, _, body, err = self.fetch(api)
            time.sleep(self.delay)
            if body and not err and st and st < 400:
                try:
                    data = json.loads(body.decode("utf-8", errors="replace"))
                    for doc in data.get("results") or []:
                        title = doc.get("title") or "Federal Register doc"
                        pdf = doc.get("pdf_url") or doc.get("full_text_xml_url")
                        if pdf and str(pdf).lower().endswith(".pdf"):
                            out.append({"url": pdf, "text": title, "is_pdf": True})
                        # html_url sometimes has pdf alternate
                        for k in ("pdf_url",):
                            if doc.get(k):
                                out.append({"url": doc[k], "text": title, "is_pdf": True})
                except Exception as e:
                    print(f"  [fr api] {e}")

        # EUR-Lex Official Journal — try latest OJ PDFs listing
        if "eur-lex.europa.eu" in host:
            # Recent OJ series L search page often embeds pdf links when fetched
            oj = "https://eur-lex.europa.eu/oj/direct-access.html"
            st, _, body, err = self.fetch(oj)
            time.sleep(self.delay)
            if body and not err:
                html = body.decode("utf-8", errors="replace")
                for link in extract_links(oj, html):
                    if link["is_pdf"] or "PDF" in (link["text"] or "").upper():
                        out.append(link)

        # Canada LEGISinfo — publications often under /DocumentViewer or PDF endpoints after following bill pages
        if "parl.ca" in host:
            # Try recent House bills list RSS if available
            for feed in (
                "https://www.parl.ca/legisinfo/en/bills/rss",
                "https://www.parl.ca/legisinfo/en/overview",
            ):
                st, _, body, err = self.fetch(feed)
                time.sleep(self.delay)
                if err or not body or (st and st >= 400):
                    continue
                html = body.decode("utf-8", errors="replace")
                for link in extract_links(feed, html):
                    if link["is_pdf"] or looks_like_bill_or_amendment(link["url"], link["text"]):
                        out.append(link)

        # NZ legislation / parliament
        if "legislation.govt.nz" in host or "parliament.nz" in host:
            st, _, body, err = self.fetch(page_url)
            time.sleep(self.delay)
            if body and not err:
                html = body.decode("utf-8", errors="replace")
                for link in extract_links(page_url, html):
                    if link["is_pdf"]:
                        out.append(link)

        # de-dupe
        seen = set()
        uniq = []
        for x in out:
            if x["url"] in seen:
                continue
            seen.add(x["url"])
            uniq.append(x)
        return uniq

    def process_source_page(
        self,
        *,
        page_url: str,
        jurisdiction: str,
        source_kind: str,
    ) -> None:
        print(f"\n==> [{jurisdiction}] {source_kind}: {page_url}")
        self.stats["sources_visited"] += 1
        status, ct, body, err = self.fetch(page_url)
        time.sleep(self.delay)
        self.stats["pages_fetched"] += 1

        if err or not body:
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {"url": page_url, "error": err or "empty", "stage": "source_page"}
            )
            print(f"  [fail page] {err or 'empty'}")
            return
        if status and status >= 400:
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {"url": page_url, "error": f"HTTP {status}", "stage": "source_page"}
            )
            print(f"  [http {status}] source page — trying site-specific APIs anyway")
            try:
                extras = self.site_specific_pdfs(page_url)
                print(f"  site-specific found {len(extras)} document links")
                downloaded_here = 0
                for pdoc in extras:
                    if downloaded_here >= self.max_pdfs_per_source:
                        break
                    if pdoc.get("is_pdf") or PDF_EXT_RE.search(pdoc["url"]):
                        rec = self.download_pdf(
                            url=pdoc["url"],
                            jurisdiction=jurisdiction,
                            source_kind=source_kind,
                            source_page=page_url,
                            title=pdoc.get("text") or pdoc["url"],
                        )
                        if rec:
                            downloaded_here += 1
                save_manifest(self.manifest)
            except Exception as e:
                print(f"  [site-specific error] {e}")
            return

        # Direct PDF landing page
        if is_pdf_url(page_url, ct) or body.startswith(b"%PDF"):
            self.download_pdf(
                url=page_url,
                jurisdiction=jurisdiction,
                source_kind=source_kind,
                source_page=page_url,
                title=Path(urlparse(page_url).path).name,
            )
            return

        try:
            html = body.decode("utf-8", errors="replace")
        except Exception:
            html = body.decode("latin-1", errors="replace")

        links = extract_links(page_url, html)
        # Merge site-specific API / feed PDF discoveries
        try:
            extra = self.site_specific_pdfs(page_url)
            if extra:
                print(f"  site-specific found {len(extra)} extra document links")
                links = extra + links
        except Exception as e:
            print(f"  [site-specific error] {e}")

        pdf_candidates = []
        follow_candidates = []

        for link in links:
            url, text = link["url"], link["text"]
            if link["is_pdf"] or PDF_EXT_RE.search(url):
                if looks_like_bill_or_amendment(url, text):
                    pdf_candidates.append(link)
            elif looks_like_bill_or_amendment(url, text):
                follow_candidates.append(link)

        # Prefer unique PDFs
        seen_pdf = set()
        unique_pdfs = []
        for p in pdf_candidates:
            if p["url"] not in seen_pdf:
                seen_pdf.add(p["url"])
                unique_pdfs.append(p)

        print(f"  found {len(unique_pdfs)} PDF links, {len(follow_candidates)} bill/amendment pages to follow")

        downloaded_here = 0
        for p in unique_pdfs:
            if downloaded_here >= self.max_pdfs_per_source:
                break
            rec = self.download_pdf(
                url=p["url"],
                jurisdiction=jurisdiction,
                source_kind=source_kind,
                source_page=page_url,
                title=p["text"] or p["url"],
            )
            if rec and not rec.get("dry_run"):
                downloaded_here += 1
            elif rec and rec.get("dry_run"):
                downloaded_here += 1

        # Follow bill detail pages one level deep to find PDFs
        follow_budget = min(self.max_follow_pages, len(follow_candidates))
        for link in follow_candidates[:follow_budget]:
            if downloaded_here >= self.max_pdfs_per_source:
                break
            detail_url = link["url"]
            # stay roughly on same host or known legislative hosts
            st, ct2, body2, err2 = self.fetch(detail_url)
            time.sleep(self.delay)
            self.stats["pages_fetched"] += 1
            if err2 or not body2 or (st and st >= 400):
                continue
            if body2.startswith(b"%PDF") or is_pdf_url(detail_url, ct2):
                rec = self.download_pdf(
                    url=detail_url,
                    jurisdiction=jurisdiction,
                    source_kind=source_kind,
                    source_page=page_url,
                    title=link["text"],
                )
                if rec:
                    downloaded_here += 1
                continue
            try:
                html2 = body2.decode("utf-8", errors="replace")
            except Exception:
                html2 = body2.decode("latin-1", errors="replace")
            for p in extract_links(detail_url, html2):
                if downloaded_here >= self.max_pdfs_per_source:
                    break
                if not (p["is_pdf"] or PDF_EXT_RE.search(p["url"])):
                    continue
                # On a bill/amendment detail page, keep every PDF
                rec = self.download_pdf(
                    url=p["url"],
                    jurisdiction=jurisdiction,
                    source_kind=source_kind,
                    source_page=detail_url,
                    title=p["text"] or link["text"],
                )
                if rec:
                    downloaded_here += 1

        # periodic save
        save_manifest(self.manifest)

    def run(self) -> None:
        rows = load_gazette()
        for row in rows:
            jurisdiction = row.get("jurisdiction") or "Unknown"
            if self.jurisdictions and jurisdiction.lower() not in self.jurisdictions:
                # allow partial match
                if not any(j in jurisdiction.lower() for j in self.jurisdictions):
                    continue

            sources: list[tuple[str, str]] = []
            for u in split_urls(row.get("parliamentary_bills")):
                sources.append(("parliamentary_bills", u))
            for u in split_urls(row.get("official_gazette")):
                sources.append(("official_gazette", u))
            if self.include_legal_db:
                for u in split_urls(row.get("legal_databases")):
                    sources.append(("legal_databases", u))

            for kind, url in sources:
                try:
                    self.process_source_page(
                        page_url=url,
                        jurisdiction=jurisdiction,
                        source_kind=kind,
                    )
                except Exception as e:
                    self.stats["errors"] += 1
                    self.manifest.setdefault("errors", []).append(
                        {
                            "url": url,
                            "jurisdiction": jurisdiction,
                            "error": str(e)[:300],
                            "stage": "process_source",
                        }
                    )
                    print(f"  [exception] {e}")
                save_manifest(self.manifest)

        print("\n===== SUMMARY =====")
        print(json.dumps(self.stats, indent=2))
        print(f"PDFs directory: {PDF_ROOT}")
        print(f"Manifest: {MANIFEST_PATH}")


def main():
    p = argparse.ArgumentParser(description="Download bill/amendment PDFs from gazette sheet links")
    p.add_argument(
        "--jurisdiction",
        action="append",
        dest="jurisdictions",
        help="Filter jurisdiction (repeatable; substring match). Default: all",
    )
    p.add_argument("--max-pdfs-per-source", type=int, default=40, help="Cap PDFs per source URL")
    p.add_argument(
        "--max-follow-pages",
        type=int,
        default=12,
        help="Max bill/detail pages to follow per source for nested PDFs",
    )
    p.add_argument("--delay", type=float, default=0.6, help="Delay between HTTP requests (seconds)")
    p.add_argument(
        "--include-legal-db",
        action="store_true",
        help="Also scrape legal_databases column (broader; more noise)",
    )
    p.add_argument("--dry-run", action="store_true", help="Discover only; do not write PDFs")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    PDF_ROOT.mkdir(parents=True, exist_ok=True)
    collector = GazettePdfCollector(
        max_pdfs_per_source=args.max_pdfs_per_source,
        max_follow_pages=args.max_follow_pages,
        delay=args.delay,
        include_legal_db=args.include_legal_db,
        jurisdictions=args.jurisdictions,
        dry_run=args.dry_run,
        timeout=args.timeout,
    )
    try:
        collector.run()
    finally:
        collector.close()


if __name__ == "__main__":
    main()

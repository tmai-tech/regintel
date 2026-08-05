#!/usr/bin/env python3
"""
Ministry document pipeline — discover full PDF list first, then download.

Flow (matches colleague excel approach):
  1. DISCOVER: sitemap + SharePoint DataSource feeds + HTML/JSON/script scan
     → master list with status=to_download
  2. DOWNLOAD: fetch each listed PDF
     → status=downloaded | download_failed | scanned_pdf

Statuses (shown on Crawl tab):
  to_download      — listed, not yet attempted
  downloaded       — file saved and is a real PDF
  download_failed  — HTTP/network/not-PDF error (error field set)
  scanned_pdf      — downloaded but little/no extractable text (likely scan)

Usage:
  python collector/ministry_pipeline.py --url https://sdaia.gov.sa \\
      --label "Saudi Arabia - SDAIA" --max-pages 500 --download
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, unquote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT))

PDF_ROOT = ROOT / "data" / "pdfs"
LISTS_DIR = PDF_ROOT / "ministry_lists"
MANIFEST_PATH = PDF_ROOT / "manifest.json"

DOC_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv")
PDF_ONLY_RE = re.compile(r"\.pdf(\.aspx)?($|\?|#|;)", re.I)
GETATTACHMENT_RE = re.compile(r"/getattachment/.*\.pdf", re.I)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Connection": "keep-alive",
}

STATUSES = ("to_download", "downloaded", "download_failed", "scanned_pdf")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def base_host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h.removeprefix("www.")


def same_site(url: str, root: str) -> bool:
    h = base_host(url)
    r = root.removeprefix("www.")
    if not h or not r:
        return False
    return h == r or h.endswith("." + r)


def normalize(url: str) -> str:
    p = urlparse(url.strip())
    path = re.sub(r"/+", "/", p.path or "/")
    q = re.sub(r"(&?(utm_[^=]+|gclid|fbclid)=[^&]*)", "", p.query).strip("&")
    return urlunparse((p.scheme or "https", p.netloc.lower(), path, "", q, ""))


def looks_like_doc(url: str) -> bool:
    path = unquote(urlparse(url).path).lower()
    if any(path.endswith(e) for e in DOC_EXTS):
        return True
    if path.endswith(".pdf.aspx") or PDF_ONLY_RE.search(url):
        return True
    if GETATTACHMENT_RE.search(url) or GETATTACHMENT_RE.search(path):
        return True
    # SharePoint / WCM often serve PDFs without .pdf in path but with .pdf in query
    if ".pdf" in url.lower() and ("/wps/wcm/" in url.lower() or "getattachment" in url.lower()):
        return True
    return False


def is_pdf_url(url: str) -> bool:
    u = url.lower()
    return ".pdf" in u or u.endswith(".pdf.aspx")


def safe_filename(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = os.path.basename(path) or "document.pdf"
    if name.lower().endswith(".aspx"):
        name = name[: -len(".aspx")]
    if not name.lower().endswith(".pdf"):
        if ".pdf" in name.lower():
            pass
        else:
            name = name + ".pdf"
    name = re.sub(r"[^\w.\-()+ ]+", "_", name).strip(" ._") or "document.pdf"
    if len(name) > 140:
        name = name[:100] + "_" + hashlib.sha256(url.encode()).hexdigest()[:8] + ".pdf"
    return name


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s or "site", flags=re.U)
    s = re.sub(r"[-\s]+", "_", s.strip()).strip("_")
    return s[:80] or "site"


class MinistryPipeline:
    def __init__(
        self,
        *,
        url: str,
        label: str,
        max_pages: int = 500,
        delay: float = 0.35,
        max_file_mb: int = 150,
        download: bool = True,
        pdf_only: bool = True,
        insecure: bool = False,
    ):
        self.start_url = normalize(url if url.startswith("http") else "https://" + url)
        self.root = base_host(self.start_url)
        self.label = label or f"Ministry - {self.root}"
        self.max_pages = max_pages
        self.delay = delay
        self.max_file_mb = max_file_mb
        self.do_download = download
        self.pdf_only = pdf_only
        self.verify = not insecure
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        self.pages_seen = 0
        self.visited_pages: set[str] = set()
        self.docs: dict[str, dict] = {}  # url -> record
        self.page_errors: list[dict] = []
        self.discovery_methods: dict[str, int] = {}
        self.datasources_found: list[str] = []
        self.sitemaps_used: list[str] = []

        LISTS_DIR.mkdir(parents=True, exist_ok=True)
        self.list_path = LISTS_DIR / f"{slugify(self.root)}.json"
        self.out_dir = PDF_ROOT / slugify(self.label) / "ministry"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    def polite(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)

    def fetch(self, url: str, timeout: float = 40) -> tuple[requests.Response | None, str | None]:
        self.polite()
        last = None
        for attempt in range(4):
            try:
                r = self.session.get(
                    url, timeout=timeout, allow_redirects=True, verify=self.verify
                )
                if r.status_code in (403, 429):
                    last = f"HTTP {r.status_code}"
                    time.sleep(2 ** attempt * 1.5)
                    continue
                if r.status_code >= 400:
                    last = f"HTTP {r.status_code}"
                    time.sleep(1.2 * (attempt + 1))
                    continue
                return r, None
            except requests.RequestException as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(2 ** attempt)
        return None, last or "unreachable"

    def add_doc(self, url: str, method: str, link_text: str = "") -> None:
        url = normalize(url)
        if not url.startswith("http"):
            return
        if self.pdf_only and not is_pdf_url(url):
            return
        if not looks_like_doc(url):
            return
        if not same_site(url, self.root):
            return
        if url in self.docs:
            return
        self.docs[url] = {
            "url": url,
            "filename": safe_filename(url),
            "type": "PDF" if is_pdf_url(url) else "DOC",
            "title": (link_text or safe_filename(url))[:200],
            "status": "to_download",
            "download_error": None,
            "jurisdiction": self.label,
            "source_kind": "ministry",
            "source_page": self.start_url,
            "host": base_host(url),
            "discovery_method": method,
            "discovered_at": now_iso(),
            "downloaded_at": None,
            "bytes": None,
            "scanned_pdf": False,
            "local_path": None,
            "sha256": None,
        }
        self.discovery_methods[method] = self.discovery_methods.get(method, 0) + 1

    # ---------- discovery ----------
    def discover_sitemaps(self) -> None:
        candidates = [
            urljoin(self.start_url, "/sitemap.xml"),
            urljoin(self.start_url, "/sitemap_index.xml"),
            urljoin(self.start_url, "/Sitemap.xml"),
            f"https://{self.root}/sitemap.xml",
            f"https://www.{self.root}/sitemap.xml",
        ]
        # robots.txt
        r, _ = self.fetch(urljoin(self.start_url, "/robots.txt"), timeout=15)
        if r and r.text:
            for line in r.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    candidates.append(line.split(":", 1)[1].strip())

        seen_sm: set[str] = set()
        queue = list(dict.fromkeys(candidates))
        while queue:
            sm = queue.pop(0)
            if sm in seen_sm:
                continue
            seen_sm.add(sm)
            r, err = self.fetch(sm, timeout=30)
            if err or r is None:
                continue
            body = r.text or ""
            if not body.strip().startswith("<") and "xml" not in (r.headers.get("Content-Type") or "").lower():
                continue
            self.sitemaps_used.append(sm)
            self.log(f"  [sitemap] {sm}")
            # loc tags
            for m in re.finditer(r"<loc>\s*([^<\s]+)\s*</loc>", body, re.I):
                loc = m.group(1).strip()
                if looks_like_doc(loc):
                    self.add_doc(loc, "sitemap")
                elif same_site(loc, self.root):
                    # page for BFS later — store as soft seed
                    if loc not in self.visited_pages:
                        self._seed_pages.append(normalize(loc))
            # nested sitemaps
            if "sitemapindex" in body.lower() or "<sitemap>" in body.lower():
                for m in re.finditer(r"<loc>\s*([^<\s]+)\s*</loc>", body, re.I):
                    loc = m.group(1).strip()
                    if "sitemap" in loc.lower() and loc not in seen_sm:
                        queue.append(loc)

    def discover_sharepoint_datasources(self, html: str, page_url: str) -> None:
        # Colleague note: DataSources/*.aspx XML feeds on SharePoint
        patterns = [
            r'["\']([^"\']*DataSources/[^"\']+\.aspx[^"\']*)["\']',
            r'["\']([^"\']*_vti_bin/[^"\']+)["\']',
            r'["\']([^"\']*_api/web/[^"\']+)["\']',
            r'["\']([^"\']*listdata\.svc[^"\']*)["\']',
        ]
        found = []
        for pat in patterns:
            for m in re.finditer(pat, html, re.I):
                u = urljoin(page_url, m.group(1))
                if same_site(u, self.root) or "sdaia" in base_host(u):
                    found.append(normalize(u))
        for ds in list(dict.fromkeys(found))[:40]:
            if ds in self.datasources_found:
                continue
            self.datasources_found.append(ds)
            self.log(f"  [datasource] {ds[:100]}")
            r, err = self.fetch(ds, timeout=45)
            if err or r is None:
                continue
            text = r.text or ""
            # extract any document-like URLs from feed
            for m in re.finditer(
                r"https?://[^\s\"'<>]+?\.(?:pdf|docx?|xlsx?)(?:\.aspx)?(?:\?[^\s\"'<>]*)?",
                text,
                re.I,
            ):
                self.add_doc(m.group(0), "datasource")
            for m in re.finditer(
                r'["\'](/[^"\']+\.pdf(?:\.aspx)?[^"\']*)["\']', text, re.I
            ):
                self.add_doc(urljoin(ds, m.group(1)), "datasource")
            # SharePoint FileRef / ServerUrl fields
            for m in re.finditer(
                r"(?:FileRef|ServerRelativeUrl|EncodedAbsUrl)[\"'>\s:=]+([^\s\"'<>]+)",
                text,
                re.I,
            ):
                path = m.group(1).strip()
                if ".pdf" in path.lower() or looks_like_doc(path):
                    self.add_doc(urljoin(ds, path) if path.startswith("/") else path, "datasource")

    def extract_from_html(self, html: str, page_url: str) -> list[str]:
        """Return same-site HTML page links to enqueue; register docs side-effect."""
        pages = []
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            target = normalize(urljoin(page_url, href))
            if not target.startswith("http"):
                continue
            text = a.get_text(" ", strip=True)[:200]
            if looks_like_doc(target):
                self.add_doc(target, "href", text)
            elif same_site(target, self.root):
                pages.append(target)
        # scripts / embedded
        for m in re.finditer(
            r"https?://[^\s\"'<>]+?\.(?:pdf|docx?|xlsx?)(?:\.aspx)?(?:\?[^\s\"'<>]*)?",
            html,
            re.I,
        ):
            self.add_doc(m.group(0), "script")
        for m in re.finditer(r'["\']([^"\']+\.pdf(?:\.aspx)?(?:\?[^"\']*)?)["\']', html, re.I):
            self.add_doc(urljoin(page_url, m.group(1)), "script")
        # SharePoint datasources on this page
        if "DataSource" in html or "_api/" in html or "_vti_bin" in html:
            self.discover_sharepoint_datasources(html, page_url)
        # JSON API hints
        for api in re.findall(r'["\'](/api/[^"\']{2,120})["\']', html)[:25]:
            pages.append(normalize(urljoin(page_url, api)))
        return pages

    def extract_from_json(self, text: str, page_url: str) -> list[str]:
        pages = []
        try:
            data = json.loads(text)
        except Exception:
            return pages

        def rec(o):
            if isinstance(o, dict):
                for v in o.values():
                    rec(v)
            elif isinstance(o, list):
                for v in o:
                    rec(v)
            elif isinstance(o, str):
                s = o.strip()
                if s.startswith("http") and looks_like_doc(s):
                    self.add_doc(s, "json_api")
                elif s.startswith("/") and looks_like_doc(s):
                    self.add_doc(urljoin(page_url, s), "json_api")
                elif s.startswith("http") and same_site(s, self.root):
                    pages.append(normalize(s))
                elif s.startswith("/api/") or (s.startswith("/") and s.count("/") >= 2):
                    low = s.lower()
                    if not low.endswith((".css", ".js", ".png", ".jpg", ".svg", ".ico")):
                        pages.append(normalize(urljoin(page_url, s)))

        rec(data)
        return pages

    def discover(self) -> dict:
        self._seed_pages: list[str] = []
        self.log(f"[discover] start {self.start_url} max_pages={self.max_pages}")
        self.discover_sitemaps()

        queue: deque[str] = deque()
        queued: set[str] = set()

        def enq(u: str):
            u = normalize(u)
            if u not in queued and same_site(u, self.root):
                queue.append(u)
                queued.add(u)

        enq(self.start_url)
        for p in getattr(self, "_seed_pages", [])[:2000]:
            enq(p)
        # common ministry / SharePoint seeds
        for path in (
            "/Documents/",
            "/en/SDAIA/about/Documents/",
            "/ar/SDAIA/about/Documents/",
            "/ndmo/Files/",
            "/en/default.aspx",
            "/ar/default.aspx",
            "/_layouts/15/",
        ):
            enq(urljoin(self.start_url, path))

        while queue and self.pages_seen < self.max_pages:
            url = queue.popleft()
            if url in self.visited_pages:
                continue
            self.visited_pages.add(url)
            self.pages_seen += 1
            if self.pages_seen % 25 == 0:
                self.log(
                    f"  [progress] pages={self.pages_seen} docs_listed={len(self.docs)} queue={len(queue)}"
                )
                self.save_list(phase="discovering")

            r, err = self.fetch(url)
            if err or r is None:
                self.page_errors.append({"url": url, "error": err})
                continue
            ct = (r.headers.get("Content-Type") or "").lower()
            # direct document
            if looks_like_doc(url) or "pdf" in ct:
                self.add_doc(url, "direct")
                continue
            text = r.text or ""
            if "json" in ct or text.lstrip()[:1] in ("{", "["):
                for p in self.extract_from_json(text, url):
                    enq(p)
                continue
            for p in self.extract_from_html(text, url):
                enq(p)
            # opportunistic datasource path probe once
            if self.pages_seen <= 5:
                for guess in (
                    urljoin(url, "DataSources/"),
                    f"https://{self.root}/_api/web/lists?$top=50",
                ):
                    enq(guess)

        stats = {
            "target_url": self.start_url,
            "label": self.label,
            "pages_visited": self.pages_seen,
            "max_pages_cap": self.max_pages,
            "documents_listed": len(self.docs),
            "sitemaps_used": self.sitemaps_used,
            "datasources_found": len(self.datasources_found),
            "discovery_methods": self.discovery_methods,
            "page_errors": len(self.page_errors),
            "hit_page_cap": self.pages_seen >= self.max_pages,
        }
        self.log(
            f"[discover] done pages={self.pages_seen} listed={len(self.docs)} "
            f"methods={self.discovery_methods} datasources={len(self.datasources_found)}"
        )
        self.save_list(phase="listed", extra_stats=stats)
        return stats

    # ---------- download ----------
    def download_one(self, rec: dict) -> None:
        url = rec["url"]
        if rec.get("status") == "downloaded" and rec.get("local_path"):
            return
        r, err = self.fetch(url, timeout=90)
        if err or r is None:
            rec["status"] = "download_failed"
            rec["download_error"] = err or "unreachable"
            return
        body = r.content or b""
        ct = (r.headers.get("Content-Type") or "").lower()
        if not body.startswith(b"%PDF") and "pdf" not in ct and is_pdf_url(url):
            # sometimes HTML error page
            rec["status"] = "download_failed"
            rec["download_error"] = f"not a PDF (ct={ct[:60]}, magic={body[:8]!r})"
            return
        if len(body) > self.max_file_mb * 1024 * 1024:
            rec["status"] = "download_failed"
            rec["download_error"] = f"file > {self.max_file_mb} MB"
            return
        fname = rec.get("filename") or safe_filename(url)
        dest = self.out_dir / fname
        if dest.exists():
            dest = self.out_dir / f"{dest.stem}_{hashlib.sha256(url.encode()).hexdigest()[:8]}.pdf"
        dest.write_bytes(body)
        sha = hashlib.sha256(body).hexdigest()[:16]
        rec["bytes"] = len(body)
        rec["sha256"] = sha
        rec["local_path"] = str(dest.relative_to(ROOT))
        rec["downloaded_at"] = now_iso()
        rec["http_status"] = r.status_code
        # scanned detection (optional light check)
        scanned = False
        try:
            import fitz

            with fitz.open(stream=body, filetype="pdf") as doc:
                text = "".join(page.get_text() for page in doc[:3])
            if len(text.strip()) < 40:
                scanned = True
        except Exception:
            scanned = False
        if scanned:
            rec["status"] = "scanned_pdf"
            rec["scanned_pdf"] = True
        else:
            rec["status"] = "downloaded"
            rec["scanned_pdf"] = False
        rec["download_error"] = None

    def download_all(self) -> dict:
        items = list(self.docs.values())
        total = len(items)
        self.log(f"[download] starting {total} documents")
        ok = fail = scanned = 0
        for i, rec in enumerate(items, 1):
            if rec["status"] not in ("to_download", "download_failed"):
                # re-attempt only to_download by default; also allow failed retry
                if rec["status"] in ("downloaded", "scanned_pdf"):
                    if rec["status"] == "scanned_pdf":
                        scanned += 1
                    else:
                        ok += 1
                    continue
            self.download_one(rec)
            if rec["status"] == "downloaded":
                ok += 1
            elif rec["status"] == "scanned_pdf":
                scanned += 1
            else:
                fail += 1
            if i % 10 == 0 or i == total:
                self.log(
                    f"  [download] {i}/{total} ok={ok} scanned={scanned} failed={fail}"
                )
                self.save_list(phase="downloading")
                self.publish_status(
                    phase="downloading",
                    message=f"downloading {i}/{total} for {self.label}",
                )
        self.merge_into_manifest()
        self.save_list(phase="complete")
        return {"downloaded": ok, "scanned_pdf": scanned, "download_failed": fail, "listed": total}

    def merge_into_manifest(self) -> None:
        """Add successfully downloaded docs into main pdfs manifest for catalog."""
        if MANIFEST_PATH.exists():
            try:
                man = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                man = {"downloads": [], "errors": [], "source_reports": [], "stats": {}}
        else:
            man = {"downloads": [], "errors": [], "source_reports": [], "stats": {}}
        by_url = {d.get("url"): d for d in (man.get("downloads") or []) if d.get("url")}
        added = 0
        for rec in self.docs.values():
            if rec["status"] not in ("downloaded", "scanned_pdf"):
                continue
            url = rec["url"]
            if url in by_url:
                by_url[url]["jurisdiction"] = self.label
                by_url[url]["source_kind"] = "ministry"
                continue
            entry = {
                "url": url,
                "jurisdiction": self.label,
                "source_kind": "ministry",
                "source_page": rec.get("source_page"),
                "title": rec.get("title") or rec.get("filename"),
                "path": rec.get("local_path"),
                "bytes": rec.get("bytes"),
                "sha256": rec.get("sha256"),
                "downloaded_at": rec.get("downloaded_at") or now_iso(),
                "status": rec["status"],
                "scanned_pdf": rec.get("scanned_pdf", False),
                "discovery_method": rec.get("discovery_method"),
            }
            man.setdefault("downloads", []).append(entry)
            by_url[url] = entry
            added += 1
        man["generated_at"] = now_iso()
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.log(f"[manifest] added {added} downloads (label={self.label})")

    def status_counts(self) -> dict:
        c = {s: 0 for s in STATUSES}
        for d in self.docs.values():
            st = d.get("status") or "to_download"
            c[st] = c.get(st, 0) + 1
        c["listed_total"] = len(self.docs)
        return c

    def save_list(self, phase: str = "running", extra_stats: dict | None = None) -> None:
        payload = {
            "updated_at": now_iso(),
            "phase": phase,
            "target_url": self.start_url,
            "label": self.label,
            "host": self.root,
            "counts": self.status_counts(),
            "discovery_methods": self.discovery_methods,
            "sitemaps_used": self.sitemaps_used,
            "datasources_found": self.datasources_found[:50],
            "pages_visited": self.pages_seen,
            "page_errors_sample": self.page_errors[:20],
            "stats": extra_stats or {},
            "documents": list(self.docs.values()),
        }
        self.list_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # slim public copy for web
        web_list = ROOT / "web" / "data" / "ministry_document_list.json"
        slim_docs = []
        for d in list(self.docs.values())[:2000]:
            slim_docs.append(
                {
                    "filename": d.get("filename"),
                    "url": d.get("url"),
                    "type": d.get("type"),
                    "status": d.get("status"),
                    "download_error": d.get("download_error"),
                    "scanned_pdf": d.get("scanned_pdf"),
                    "title": d.get("title"),
                    "bytes": d.get("bytes"),
                    "discovery_method": d.get("discovery_method"),
                    "jurisdiction": d.get("jurisdiction"),
                }
            )
        web_payload = {
            "updated_at": payload["updated_at"],
            "phase": phase,
            "target_url": self.start_url,
            "label": self.label,
            "counts": payload["counts"],
            "discovery_methods": self.discovery_methods,
            "pages_visited": self.pages_seen,
            "documents": slim_docs,
            "failed_sample": [
                d
                for d in slim_docs
                if d.get("status") == "download_failed"
            ][:50],
        }
        web_list.parent.mkdir(parents=True, exist_ok=True)
        web_list.write_text(
            json.dumps(web_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def publish_status(self, phase: str, message: str) -> None:
        try:
            from live_publish import publish

            counts = self.status_counts()
            publish(
                phase=phase,
                message=message,
                current_source={
                    "jurisdiction": self.label,
                    "url": self.start_url,
                    "source_kind": "ministry_pipeline",
                    "listed": counts.get("listed_total", 0),
                    "downloaded": counts.get("downloaded", 0),
                    "download_failed": counts.get("download_failed", 0),
                    "scanned_pdf": counts.get("scanned_pdf", 0),
                    "to_download": counts.get("to_download", 0),
                },
                force_git=False,
            )
            # enrich crawl_status with ministry list summary
            status_path = ROOT / "web" / "data" / "crawl_status.json"
            if status_path.exists():
                st = json.loads(status_path.read_text(encoding="utf-8"))
                st["ministry_document_list"] = {
                    "label": self.label,
                    "target_url": self.start_url,
                    "counts": counts,
                    "discovery_methods": self.discovery_methods,
                    "pages_visited": self.pages_seen,
                    "list_file": "data/ministry_document_list.json",
                    "updated_at": now_iso(),
                }
                st["totals"] = st.get("totals") or {}
                st["totals"]["ministry_listed"] = counts.get("listed_total", 0)
                st["totals"]["ministry_downloaded"] = counts.get("downloaded", 0)
                st["totals"]["ministry_failed"] = counts.get("download_failed", 0)
                st["totals"]["ministry_scanned"] = counts.get("scanned_pdf", 0)
                st["totals"]["ministry_to_download"] = counts.get("to_download", 0)
                status_path.write_text(
                    json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                (ROOT / "data" / "pdfs" / "crawl_status.json").write_text(
                    status_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
        except Exception as e:
            self.log(f"[publish] {e}")

    def run(self) -> dict:
        t0 = time.time()
        self.publish_status("discovering", f"discovering documents on {self.start_url}")
        dstats = self.discover()
        self.publish_status(
            "listed",
            f"listed {len(self.docs)} documents on {self.root}",
        )
        dl_stats = {}
        if self.do_download and self.docs:
            self.publish_status("downloading", f"downloading {len(self.docs)} listed docs")
            dl_stats = self.download_all()
            try:
                from live_publish import publish

                publish(
                    phase="idle",
                    message=(
                        f"{self.label}: listed={dl_stats.get('listed')} "
                        f"downloaded={dl_stats.get('downloaded')} "
                        f"scanned={dl_stats.get('scanned_pdf')} "
                        f"failed={dl_stats.get('download_failed')}"
                    ),
                    force_git=True,
                )
            except Exception as e:
                self.log(f"[publish final] {e}")
        elapsed = round(time.time() - t0, 1)
        counts = self.status_counts()
        result = {
            "elapsed_sec": elapsed,
            "discover": dstats,
            "counts": counts,
            "download": dl_stats,
            "list_path": str(self.list_path),
        }
        self.log(f"[done] {json.dumps(result, indent=2)}")
        return result


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Ministry discover-then-download pipeline")
    ap.add_argument("--url", required=True, help="Ministry site root URL")
    ap.add_argument("--label", default="", help='Jurisdiction label e.g. "Saudi Arabia - SDAIA"')
    ap.add_argument("--max-pages", type=int, default=500)
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--max-file-mb", type=int, default=150)
    ap.add_argument("--discover-only", action="store_true", help="List only, do not download")
    ap.add_argument("--download", action="store_true", default=True, help="Download after list")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--insecure", action="store_true")
    args = ap.parse_args()
    download = args.download and not args.no_download and not args.discover_only
    label = args.label or f"Ministry - {base_host(args.url)}"
    pipe = MinistryPipeline(
        url=args.url,
        label=label,
        max_pages=args.max_pages,
        delay=args.delay,
        max_file_mb=args.max_file_mb,
        download=download,
        insecure=args.insecure,
    )
    pipe.run()


if __name__ == "__main__":
    main()

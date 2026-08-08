#!/usr/bin/env python3
"""
Ministry document pipeline — discover full PDF list first, then download.

Independent of any Excel seed. Mirrors colleague Extraction_Script + ministry_crawler:
  1. DISCOVER:
     - site nav API (sdaiaapi) for full page tree
     - sitemap.xml
     - SharePoint DataSources / _api when WAF allows
     - priority BFS (KnowledgeCenter / MediaCenter first)
     - href + script/JSON harvest (colleague walk_json)
     - Playwright JS-render fallback for SPA shells (colleague Extraction_Script)
       with network interception for .pdf URLs
  2. DOWNLOAD: each listed PDF → downloaded | download_failed | scanned_pdf

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
import socket
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, unquote

import requests
from bs4 import BeautifulSoup
import urllib3
import urllib3.util.connection as urllib3_cn

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT))

PDF_ROOT = ROOT / "data" / "pdfs"
LISTS_DIR = PDF_ROOT / "ministry_lists"
MANIFEST_PATH = PDF_ROOT / "manifest.json"

DOC_EXTS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv")
PDF_ONLY_RE = re.compile(r"\.pdf(\.aspx)?($|\?|#|;)", re.I)
GETATTACHMENT_RE = re.compile(r"/getattachment/.*\.pdf", re.I)
# TGA / some Saudi CMS serve real PDFs at opaque file endpoints (no .pdf suffix).
CMS_FILE_RE = re.compile(
    r"/(websitefile|sharedfile|downloadfile|getfile|filedownload|download\.ashx)"
    r"(/|$|\?)",
    re.I,
)

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
    scheme = p.scheme or "https"
    netloc = (p.netloc or "").lower()
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    path = re.sub(r"/+", "/", p.path or "/")
    q = re.sub(r"(&?(utm_[^=]+|gclid|fbclid)=[^&]*)", "", p.query).strip("&")
    return urlunparse((scheme, netloc, path, "", q, ""))


def flip_www(url: str) -> str:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if not host:
        return url
    if host.startswith("www."):
        new_host = host[4:]
    else:
        new_host = "www." + host
    netloc = new_host
    if p.port and p.port not in (80, 443):
        netloc = f"{new_host}:{p.port}"
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


def start_url_candidates(url: str) -> list[str]:
    u = normalize(url if url.startswith("http") else "https://" + url)
    p = urlparse(u)
    host = (p.hostname or "").lower()
    bare = host.removeprefix("www.")
    hosts = [host, bare, "www." + bare]
    out = [u]
    for h in hosts:
        for path in ("/", "/en/", "/ar/", "/en", "/ar"):
            out.append(f"https://{h}{path}")
    return list(dict.fromkeys(out))


def force_ipv4() -> None:
    """GitHub-hosted runners often fail Saudi .gov.sa AAAA (Errno 101 unreachable)."""
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET


def looks_like_doc(url: str) -> bool:
    path = unquote(urlparse(url).path).lower()
    if any(path.endswith(e) for e in DOC_EXTS):
        return True
    if path.endswith(".pdf.aspx") or PDF_ONLY_RE.search(url):
        return True
    if GETATTACHMENT_RE.search(url) or GETATTACHMENT_RE.search(path):
        return True
    if CMS_FILE_RE.search(path) or CMS_FILE_RE.search(url):
        return True
    # SharePoint / WCM often serve PDFs without .pdf in path but with .pdf in query
    if ".pdf" in url.lower() and ("/wps/wcm/" in url.lower() or "getattachment" in url.lower()):
        return True
    return False


def is_pdf_url(url: str) -> bool:
    u = url.lower()
    return ".pdf" in u or u.endswith(".pdf.aspx") or bool(CMS_FILE_RE.search(u))


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
        max_pages: int = 2000,
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
        force_ipv4()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        self.pages_seen = 0
        self.visited_pages: set[str] = set()
        self.docs: dict[str, dict] = {}  # url -> record
        self.page_errors: list[dict] = []
        self.discovery_methods: dict[str, int] = {}
        self.datasources_found: list[str] = []
        self.sitemaps_used: list[str] = []
        self._waf_blocks = 0
        self._playwright = None  # lazy PlaywrightRenderer
        self._pw_browser = None
        self._pw_renders = 0
        self._pw_max_renders = 80 if "sdaia" in self.root else 25
        self._site_reachable = True
        self._consecutive_errors = 0

        LISTS_DIR.mkdir(parents=True, exist_ok=True)
        self.list_path = LISTS_DIR / f"{slugify(self.root)}.json"
        self.out_dir = PDF_ROOT / slugify(self.label) / "ministry"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    def polite(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)

    @staticmethod
    def _is_waf_reject(r: requests.Response | None) -> bool:
        if r is None:
            return False
        body = (r.text or "")[:400]
        return (
            "Request Rejected" in body
            or "support ID is" in body
            or (r.status_code == 200 and len(r.content or b"") < 400 and "<html>" in body.lower() and "rejected" in body.lower())
        )

    def fetch(self, url: str, timeout: float = 40) -> tuple[requests.Response | None, str | None]:
        self.polite()
        last = None
        tried_alt = False
        for attempt in range(3):
            try:
                r = self.session.get(
                    url, timeout=timeout, allow_redirects=True, verify=self.verify
                )
                if self._is_waf_reject(r):
                    self._waf_blocks += 1
                    last = "WAF rejected"
                    time.sleep(min(2 ** attempt * 1.2, 6))
                    continue
                if r.status_code in (403, 429):
                    last = f"HTTP {r.status_code}"
                    time.sleep(min(2 ** attempt * 1.5, 8))
                    continue
                if r.status_code >= 400:
                    last = f"HTTP {r.status_code}"
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return r, None
            except requests.exceptions.SSLError as e:
                last = f"SSLError: {e}"
                if self.verify:
                    self.verify = False
                    self.log(f"  [tls] verify=False after SSLError on {base_host(url)}")
                    continue
                time.sleep(1.0 * (attempt + 1))
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last = f"{type(e).__name__}: {e}"
                if not tried_alt:
                    alt = flip_www(url)
                    if alt != url:
                        self.log(f"  [net] retry alt host {alt[:90]}")
                        url = alt
                        tried_alt = True
                        continue
                time.sleep(min(2 ** attempt, 6))
            except requests.RequestException as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(min(2 ** attempt, 6))
        return None, last or "unreachable"

    def resolve_start(self) -> bool:
        """Pick a reachable homepage (www /apex /en /ar) before burning the BFS budget."""
        for cand in start_url_candidates(self.start_url):
            r, err = self.fetch(cand, timeout=20)
            if r is not None and not err:
                final = normalize(r.url or cand)
                # keep a site root, not a random deep redirect
                p = urlparse(final)
                path = p.path if p.path in ("/", "/en", "/en/", "/ar", "/ar/") else "/"
                self.start_url = normalize(f"{p.scheme}://{p.netloc}{path}")
                self.root = base_host(self.start_url)
                self._site_reachable = True
                self.log(f"[start] reachable {self.start_url} (tried {cand})")
                return True
        self._site_reachable = False
        self.log(f"[start] UNREACHABLE {self.start_url} — skip deep discover")
        return False

    def _looks_sharepoint(self, html: str, headers=None) -> bool:
        blob = (html or "")[:12000].lower()
        if any(k in blob for k in ("sharepoint", "_api/web", "_layouts/15", "microsoftsharepoint")):
            return True
        if headers:
            joined = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
            if "microsoftsharepoint" in joined or "sprequestguid" in joined:
                return True
        return False

    def looks_like_spa_shell(self, html: str, url: str) -> bool:
        """Colleague Extraction_Script heuristic: empty SPA / JS-only library pages."""
        if not html or len(html) < 2000:
            return True
        low = html.lower()
        if "request rejected" in low:
            return False
        a_count = low.count("<a ")
        # KnowledgeCenter / MediaCenter shells often have almost no document links
        u = url.lower()
        library = any(
            k in u
            for k in (
                "knowledgecenter",
                "ainewsletter",
                "mediacenter",
                "researchlibrary",
                "sdaiapublications",
                "ai-newsletter",
            )
        )
        if library and a_count < 8 and ".pdf" not in low:
            return True
        spa_markers = ('id="root"', 'id="app"', 'id="__next"', "ng-version")
        if any(m in low for m in spa_markers) and a_count < 5:
            return True
        return False

    def playwright_discover(self, url: str) -> list[str]:
        """JS-render page (colleague Extraction_Script) + capture PDF network URLs."""
        pages: list[str] = []
        if self._pw_renders >= self._pw_max_renders:
            return pages
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.log("  [playwright] not installed — skip JS render")
            return pages
        self._pw_renders += 1
        self.log(f"  [playwright] render {url[:100]}")
        pdf_hits: list[str] = []
        try:
            if self._playwright is None:
                self._playwright = sync_playwright().start()
            if self._pw_browser is None:
                self._pw_browser = self._playwright.chromium.launch(
                    headless=True,
                    args=["--disable-ipv6", "--ignore-certificate-errors"],
                )
            browser = self._pw_browser
            try:
                context = browser.new_context(user_agent=UA, locale="en-US", ignore_https_errors=True)
                page = context.new_page()

                def on_response(res):
                    try:
                        u = res.url
                        ct = (res.headers.get("content-type") or "").lower()
                        if ".pdf" in u.lower() or "application/pdf" in ct:
                            pdf_hits.append(u)
                        # harvest JSON APIs that list files
                        if any(
                            k in u
                            for k in ("_api/", "DataSource", "sdaiaapi", "listdata")
                        ):
                            try:
                                body = res.text()
                                self.harvest_doc_urls_from_text(body, u, "playwright_api")
                            except Exception:
                                pass
                    except Exception:
                        pass

                page.on("response", on_response)
                try:
                    goto_ms = 45000 if "sdaia" in self.root else 25000
                    page.goto(url, timeout=goto_ms, wait_until="domcontentloaded")
                    page.wait_for_timeout(1800 if "sdaia" in self.root else 1200)
                    for _ in range(3 if "sdaia" in self.root else 2):
                        page.mouse.wheel(0, 1800)
                        page.wait_for_timeout(400)
                    html = page.content()
                except Exception as e:
                    self.log(f"  [playwright] goto fail: {e}")
                    html = ""
                context.close()
            except Exception:
                html = ""
                try:
                    context.close()
                except Exception:
                    pass
            for u in pdf_hits:
                self.add_doc(u, "playwright_net")
            if html:
                pages = self.extract_from_html(html, url)
                self.harvest_doc_urls_from_text(html, url, "playwright_html")
        except Exception as e:
            self.log(f"  [playwright] error: {e}")
            self._pw_browser = None
        return pages

    def discover_nav_api(self) -> None:
        """SDAIA custom nav API — full page tree (independent of Excel)."""
        if "sdaia" not in self.root:
            return
        for path in (
            "/sdaiaapi/api/home/geteninternalpagenavdata",
            "/sdaiaapi/api/home/getinternalpagenavdata",
        ):
            url = f"https://{self.root}{path}"
            r, err = self.fetch(url, timeout=40)
            if err or r is None:
                continue
            try:
                data = r.json()
            except Exception:
                continue
            n_before = len(getattr(self, "_seed_pages", []))
            found = 0

            def walk(o):
                nonlocal found
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k.lower() in ("url", "href", "link", "path") and isinstance(v, str):
                            if v.startswith("/") or v.startswith("http"):
                                full = normalize(urljoin(f"https://{self.root}/", v))
                                if same_site(full, self.root) or "sdaia" in base_host(full):
                                    self._seed_pages.append(full)
                                    found += 1
                                    if looks_like_doc(full):
                                        self.add_doc(full, "nav_api")
                        walk(v)
                elif isinstance(o, list):
                    for i in o:
                        walk(i)

            walk(data)
            self.log(f"  [nav_api] {path} → {found} urls (seeds now {len(self._seed_pages)})")


    def add_doc(self, url: str, method: str, link_text: str = "") -> None:
        url = normalize(url)
        if not url.startswith("http"):
            return
        if self.pdf_only and not is_pdf_url(url):
            return
        if not looks_like_doc(url):
            return
        # same site or sibling portal (dgp.sdaia.gov.sa under sdaia.gov.sa)
        h = base_host(url)
        r = self.root
        ok = same_site(url, r)
        if r.endswith("sdaia.gov.sa") and h.endswith("sdaia.gov.sa"):
            ok = True
        if not ok:
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
    def deep_seed_paths(self) -> list[str]:
        """High-value library paths (colleague excel: KnowledgeCenter holds most PDFs)."""
        common = [
            "/Documents/",
            "/en/default.aspx",
            "/ar/default.aspx",
            "/en/",
            "/ar/",
            "/_layouts/15/",
            "/_api/web/lists?$select=Title,Id,ItemCount,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=200",
            "/_api/web/lists?$filter=BaseTemplate eq 101&$top=100",
            "/_vti_bin/listdata.svc/",
            "/_api/search/query?querytext=%27FileExtension:pdf%27&rowlimit=500",
            "/_api/search/query?querytext=%27FileType:pdf%27&rowlimit=500",
        ]
        if "sdaia" in self.root:
            common.extend(
                [
                    # KnowledgeCenter / MediaCenter (colleague Excel bulk lives here)
                    "/en/MediaCenter/KnowledgeCenter/",
                    "/ar/MediaCenter/KnowledgeCenter/",
                    "/en/MediaCenter/KnowledgeCenter/Pages/default.aspx",
                    "/ar/MediaCenter/KnowledgeCenter/Pages/default.aspx",
                    "/en/MediaCenter/KnowledgeCenter/Pages/AI-Newsletter.aspx",
                    "/ar/MediaCenter/KnowledgeCenter/Pages/AI-Newsletter.aspx",
                    "/en/MediaCenter/KnowledgeCenter/Pages/SDAIAPublications.aspx",
                    "/ar/MediaCenter/KnowledgeCenter/Pages/SDAIAPublications.aspx",
                    "/en/MediaCenter/KnowledgeCenter/AINewsletter/",
                    "/ar/MediaCenter/KnowledgeCenter/AINewsletter/",
                    "/en/MediaCenter/KnowledgeCenter/ResearchLibrary/",
                    "/ar/MediaCenter/KnowledgeCenter/ResearchLibrary/",
                    "/en/MediaCenter/",
                    "/ar/MediaCenter/",
                    "/en/MediaCenter/Pages/default.aspx",
                    "/ar/MediaCenter/Pages/default.aspx",
                    "/en/MediaCenter/News/Pages/default.aspx",
                    "/ar/MediaCenter/News/Pages/default.aspx",
                    "/en/MediaCenter/Events/Pages/default.aspx",
                    "/ar/MediaCenter/Events/Pages/default.aspx",
                    "/en/MediaCenter/Initiatives/Pages/default.aspx",
                    "/ar/MediaCenter/Initiatives/Pages/default.aspx",
                    # Document libraries
                    "/en/SDAIA/about/Documents/",
                    "/ar/SDAIA/about/Documents/",
                    "/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx",
                    "/ar/SDAIA/about/Pages/RegulationsAndPolicies.aspx",
                    "/en/SDAIA/about/",
                    "/ar/SDAIA/about/",
                    "/en/SDAIA/eParticipation/",
                    "/ar/SDAIA/eParticipation/",
                    "/en/Sectors/Nic/",
                    "/ar/Sectors/Nic/",
                    "/en/Sectors/",
                    "/ar/Sectors/",
                    "/en/Research/",
                    "/ar/Research/",
                    "/en/Research/Documents/",
                    "/ar/Research/Documents/",
                    "/en/Research/Pages/default.aspx",
                    "/ar/Research/Pages/default.aspx",
                    "/ndmo/Files/",
                    "/Documents/",
                    "/en/DataSources/Tags.aspx",
                    "/ar/DataSources/Tags.aspx",
                    "https://dgp.sdaia.gov.sa/",
                ]
            )
        if "tga.gov.sa" in self.root:
            common.extend(
                [
                    "/en/",
                    "/ar/",
                    "/en/regulations",
                    "/ar/regulations",
                    "/en/legislation",
                    "/ar/legislation",
                    "/en/library",
                    "/ar/library",
                    "/en/media",
                    "/ar/media",
                    "/en/opendata",
                    "/ar/opendata",
                ]
            )
        if "mc.gov.sa" in self.root:
            common.extend(
                [
                    "/ar/Documents/",
                    "/en/Documents/",
                    "/DOC/",
                    "/ar/mediacenter/",
                    "/ar/mediacenter/Documents/",
                    "/ar/eservices/Documents/",
                    "/ar/DO/",
                    "/ar/CC/D/",
                    "/ar/Regulations/",
                    "/en/Regulations/",
                    "https://regulations.mc.gov.sa/",
                ]
            )
        if "mewa.gov.sa" in self.root:
            common.extend(
                [
                    "/ar/InformationCenter/DocsCenter/RulesLibrary/",
                    "/en/InformationCenter/DocsCenter/RulesLibrary/",
                    "/ar/InformationCenter/DocsCenter/RulesLibrary/Documents/",
                    "/en/InformationCenter/DocsCenter/RulesLibrary/Docs/",
                    "/ar/Documents/",
                    "/en/Documents/",
                    "/ar/Documents/Mewa/",
                    "/ar/Ministry/AboutMinistry/Documents/",
                    "/ar/Ministry/initiatives/SectorStratigy/Reports/",
                    "/ar/Ministry/Agencies/AgencyForInnovation/Documents/",
                    "/ar/InformationCenter/",
                    "/en/InformationCenter/",
                ]
            )
        return common

    def discover_sitemaps(self) -> None:
        candidates = [
            urljoin(self.start_url, "/sitemap.xml"),
            urljoin(self.start_url, "/sitemap_index.xml"),
            urljoin(self.start_url, "/Sitemap.xml"),
            f"https://{self.root}/sitemap.xml",
            f"https://www.{self.root}/sitemap.xml",
            f"https://{self.root}/sitemap_index.xml",
            f"https://{self.root}/_layouts/15/sitemap.aspx",
            f"https://{self.root}/en/sitemap.xml",
            f"https://{self.root}/ar/sitemap.xml",
        ]
        r, _ = self.fetch(urljoin(self.start_url, "/robots.txt"), timeout=15)
        if r and r.text:
            for line in r.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    candidates.append(line.split(":", 1)[1].strip())

        seen_sm: set[str] = set()
        queue = list(dict.fromkeys(candidates))
        while queue:
            sm = queue.pop(0)
            if sm in seen_sm or len(seen_sm) > 80:
                continue
            seen_sm.add(sm)
            r, err = self.fetch(sm, timeout=45)
            if err or r is None:
                continue
            body = r.text or ""
            ct = (r.headers.get("Content-Type") or "").lower()
            if not (
                body.strip().startswith("<")
                or "xml" in ct
                or "<urlset" in body.lower()
                or "<sitemapindex" in body.lower()
                or "<loc>" in body.lower()
            ):
                if "html" in ct or "<html" in body[:500].lower():
                    for p in self.extract_from_html(body, sm):
                        self._seed_pages.append(p)
                continue
            self.sitemaps_used.append(sm)
            self.log(f"  [sitemap] {sm}")
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body, re.I)
            locs += re.findall(r"https?://[^\s\"'<>]+", body)
            for loc in locs:
                loc = loc.strip()
                if looks_like_doc(loc):
                    self.add_doc(loc, "sitemap")
                elif same_site(loc, self.root):
                    if "sitemap" in loc.lower() and loc not in seen_sm:
                        queue.append(loc)
                    else:
                        self._seed_pages.append(normalize(loc))

    def harvest_doc_urls_from_text(self, text: str, base: str, method: str) -> None:
        if not text:
            return
        for m in re.finditer(
            r"https?://[^\s\"'<>]+?\.(?:pdf|docx?|xlsx?|pptx?)(?:\.aspx)?(?:\?[^\s\"'<>]*)?",
            text,
            re.I,
        ):
            self.add_doc(m.group(0).replace("&amp;", "&"), method)
        for m in re.finditer(
            r'["\']([^"\']+\.pdf(?:\.aspx)?(?:\?[^"\']*)?)["\']', text, re.I
        ):
            self.add_doc(urljoin(base, m.group(1).replace("&amp;", "&")), method)
        for m in re.finditer(
            r"(?:href|src|url|FileRef|ServerRelativeUrl|EncodedAbsUrl|Path)\s*[=:]\s*[\"']?([^\s\"'<>]+\.pdf[^\s\"'<>]*)",
            text,
            re.I,
        ):
            path = m.group(1).replace("&amp;", "&")
            self.add_doc(urljoin(base, path) if path.startswith("/") else path, method)
        for m in re.finditer(r"(/[^\s\"'<>]*?/[^\s\"'<>]*?\.pdf)", text, re.I):
            self.add_doc(urljoin(base, m.group(1)), method)

    def discover_sharepoint_datasources(self, html: str, page_url: str) -> None:
        if not getattr(self, "_site_reachable", True):
            return
        patterns = [
            r'["\']([^"\']*DataSources/[^"\']+\.aspx[^"\']*)["\']',
            r'["\']([^"\']*_vti_bin/[^"\']+)["\']',
            r'["\']([^"\']*_api/web/[^"\']+)["\']',
            r'["\']([^"\']*_api/search/[^"\']+)["\']',
            r'["\']([^"\']*listdata\.svc[^"\']*)["\']',
        ]
        found = []
        for pat in patterns:
            for m in re.finditer(pat, html or "", re.I):
                u = urljoin(page_url, m.group(1).replace("&amp;", "&"))
                if same_site(u, self.root):
                    found.append(normalize(u))
        probes = [
            f"https://{self.root}/_api/web/lists?$select=Title,Id,ItemCount,BaseTemplate,RootFolder/ServerRelativeUrl&$expand=RootFolder&$top=200",
            f"https://{self.root}/_api/search/query?querytext=%27FileExtension:pdf%20Path:{self.root}%27&rowlimit=500&selectproperties=%27Path,Title,Size%27",
            f"https://{self.root}/_api/search/query?querytext=%27FileType:pdf%27&rowlimit=500",
            f"https://{self.root}/_vti_bin/listdata.svc/",
            f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/Documents')/files?$top=500",
            f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/en')/files?$top=200",
            f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/Documents')/files?$top=500",
            f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/en/Documents')/files?$top=500",
        ]
        if "sdaia" in self.root:
            probes.extend(
                [
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/en/MediaCenter')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/MediaCenter')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/en/MediaCenter/KnowledgeCenter')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/MediaCenter/KnowledgeCenter')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/en/MediaCenter/KnowledgeCenter/AINewsletter')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/MediaCenter/KnowledgeCenter/AINewsletter')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/en/MediaCenter/KnowledgeCenter/ResearchLibrary')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/MediaCenter/KnowledgeCenter/ResearchLibrary')/files?$top=500",
                ]
            )
        if "mewa" in self.root:
            probes.extend(
                [
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/InformationCenter/DocsCenter/RulesLibrary/Documents')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/en/InformationCenter/DocsCenter/RulesLibrary/Docs')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/Ministry/AboutMinistry/Documents')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/Ministry/initiatives/SectorStratigy/Reports')/files?$top=500",
                ]
            )
        if "mc.gov.sa" in self.root:
            probes.extend(
                [
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/mediacenter/Documents')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/DOC')/files?$top=500",
                    f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('/ar/eservices/Documents')/files?$top=500",
                ]
            )
        for probe in probes:
            found.append(probe)

        for ds in list(dict.fromkeys(found))[:120]:
            if ds in self.datasources_found:
                continue
            self.datasources_found.append(ds)
            self.log(f"  [datasource] {ds[:130]}")
            r, err = self.fetch(ds, timeout=60)
            if err or r is None:
                continue
            text = r.text or ""
            self.harvest_doc_urls_from_text(text, ds, "datasource")
            for m in re.finditer(r'"ServerRelativeUrl"\s*:\s*"([^"]+)"', text):
                rel = m.group(1)
                if any(
                    x in rel.lower()
                    for x in (
                        "document", "media", "library", "pdf", "file",
                        "knowledge", "research", "publication", "newsletter",
                        "sdaia", "sector",
                    )
                ):
                    api = f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('{rel}')/files?$top=500"
                    if api not in self.datasources_found:
                        self.datasources_found.append(api)
                        r2, err2 = self.fetch(api, timeout=60)
                        if r2 and not err2:
                            self.harvest_doc_urls_from_text(r2.text or "", api, "datasource")
                    sub = f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('{rel}')/folders?$top=200"
                    r3, err3 = self.fetch(sub, timeout=45)
                    if r3 and not err3:
                        for m2 in re.finditer(r'"ServerRelativeUrl"\s*:\s*"([^"]+)"', r3.text or ""):
                            rel2 = m2.group(1)
                            api2 = f"https://{self.root}/_api/web/getfolderbyserverrelativeurl('{rel2}')/files?$top=500"
                            if api2 in self.datasources_found:
                                continue
                            self.datasources_found.append(api2)
                            r4, err4 = self.fetch(api2, timeout=60)
                            if r4 and not err4:
                                self.harvest_doc_urls_from_text(r4.text or "", api2, "datasource")

    def extract_from_html(self, html: str, page_url: str) -> list[str]:
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
        for tag in soup.find_all(["iframe", "embed", "object", "source"]):
            for attr in ("src", "data", "data-src"):
                if tag.get(attr):
                    t = normalize(urljoin(page_url, tag.get(attr)))
                    if looks_like_doc(t):
                        self.add_doc(t, "embed")
        self.harvest_doc_urls_from_text(html, page_url, "script")
        if (
            "DataSource" in html
            or "_api/" in html
            or "_vti_bin" in html
            or "SharePoint" in html
            or "WebPart" in html
            or ("sdaia" in self.root and self.pages_seen <= 5)
        ):
            self.discover_sharepoint_datasources(html, page_url)
        for api in re.findall(r'["\'](/_api/[^"\']{2,200})["\']', html)[:40]:
            pages.append(normalize(urljoin(page_url, api)))
        for api in re.findall(r'["\'](/api/[^"\']{2,120})["\']', html)[:25]:
            pages.append(normalize(urljoin(page_url, api)))
        return pages

    def extract_from_json(self, text: str, page_url: str) -> list[str]:
        pages = []
        self.harvest_doc_urls_from_text(text, page_url, "json_api")
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
                elif s.startswith("/_api/") or s.startswith("/api/") or (
                    s.startswith("/") and s.count("/") >= 2
                ):
                    low = s.lower()
                    if not low.endswith((".css", ".js", ".png", ".jpg", ".svg", ".ico", ".woff")):
                        pages.append(normalize(urljoin(page_url, s)))

        rec(data)
        return pages

    def page_priority(self, url: str) -> int:
        u = url.lower()
        if any(
            k in u
            for k in (
                "knowledgecenter", "ainewsletter", "researchlibrary",
                "/documents", "regulations", "policies", "mediacenter",
                "datasource", "_api/", "newsletter",
                "ruleslibrary", "docscenter", "websitefile", "sharedfile",
                "legislation", "/doc/", "infocenter",
            )
        ):
            return 0
        if any(k in u for k in ("/about", "/sectors", "/research", "eparticipation", "informationcenter")):
            return 1
        return 2

    def discover(self) -> dict:
        self._seed_pages: list[str] = []
        self.log(f"[discover] start {self.start_url} max_pages={self.max_pages}")
        reachable = self.resolve_start()
        if not reachable:
            self.playwright_discover(self.start_url)
            if not self.docs:
                stats = {
                    "target_url": self.start_url,
                    "label": self.label,
                    "pages_visited": self.pages_seen,
                    "documents_listed": 0,
                    "page_errors": len(self.page_errors),
                    "unreachable": True,
                }
                self.log("[discover] abort: homepage unreachable")
                self.save_list(phase="listed", extra_stats=stats)
                self.publish_status(
                    "listed",
                    f"listed 0 documents on {self.root} (unreachable)",
                    force_git=True,
                )
                return stats
        # Warm session (cookies) — reduces intermittent WAF empties
        home, home_err = self.fetch(self.start_url, timeout=30)
        home_html = home.text if home is not None and not home_err else ""
        self.discover_nav_api()
        self.discover_sitemaps()
        # SharePoint probes only when the site looks like SharePoint (or SDAIA)
        if self._site_reachable and self._waf_blocks < 15 and (
            "sdaia" in self.root or self._looks_sharepoint(home_html, getattr(home, "headers", None))
        ):
            self.discover_sharepoint_datasources(home_html, self.start_url)

        queues: dict[int, deque] = {0: deque(), 1: deque(), 2: deque()}
        queued: set[str] = set()

        def enq(u: str):
            u = normalize(u)
            if not u.startswith("http") or u in queued:
                return
            h = base_host(u)
            if not same_site(u, self.root):
                # sibling portals e.g. dgp.sdaia.gov.sa
                if not (
                    h.endswith(".sdaia.gov.sa")
                    or h == "sdaia.gov.sa"
                    or (self.root in h or h.endswith("." + self.root))
                ):
                    return
            queued.add(u)
            queues[self.page_priority(u)].append(u)

        def pop_next():
            for prio in (0, 1, 2):
                if queues[prio]:
                    return queues[prio].popleft()
            return None

        enq(self.start_url)
        for p in getattr(self, "_seed_pages", [])[:8000]:
            enq(p)
        for path in self.deep_seed_paths():
            if path.startswith("http"):
                enq(path)
            else:
                enq(urljoin(self.start_url, path))
                enq(f"https://{self.root}{path}")

        while self.pages_seen < self.max_pages:
            url = pop_next()
            if not url:
                break
            if url in self.visited_pages:
                continue
            self.visited_pages.add(url)
            self.pages_seen += 1
            if self.pages_seen % 25 == 0:
                qsize = sum(len(q) for q in queues.values())
                self.log(
                    f"  [progress] pages={self.pages_seen} docs_listed={len(self.docs)} "
                    f"queue={qsize} methods={self.discovery_methods} "
                    f"pw={self._pw_renders} waf={self._waf_blocks}"
                )
                self.publish_status(
                    "discovering",
                    f"discovering {self.root}: pages={self.pages_seen} listed={len(self.docs)}",
                )

            # Skip known-dead SharePoint REST if WAF keeps rejecting
            if "/_api/" in url and self._waf_blocks > 20:
                continue

            r, err = self.fetch(url)
            text = ""
            ct = ""
            if err or r is None:
                self.page_errors.append({"url": url, "error": err})
                self._consecutive_errors += 1
                if (
                    self._consecutive_errors >= 20
                    and len(self.docs) == 0
                    and self.pages_seen >= 12
                ):
                    self.log("[discover] abort: 0 docs after 12+ consecutive fetch failures")
                    break
                # Colleague path: try Playwright when plain HTTP fails on library pages
                # Skip _api (Playwright cannot help) and stop after a run of failures.
                if (
                    self.page_priority(url) == 0
                    and "/_api/" not in url
                    and "/_vti_bin/" not in url
                    and self._consecutive_errors < 8
                ):
                    for p in self.playwright_discover(url):
                        enq(p)
                continue
            self._consecutive_errors = 0
            ct = (r.headers.get("Content-Type") or "").lower()
            if looks_like_doc(url) or "pdf" in ct:
                self.add_doc(url, "direct")
                continue
            text = r.text or ""
            if "json" in ct or text.lstrip()[:1] in ("{", "["):
                for p in self.extract_from_json(text, url):
                    enq(p)
                continue
            if "xml" in ct or text.lstrip().startswith("<?xml") or "<feed" in text[:200].lower():
                self.harvest_doc_urls_from_text(text, url, "datasource")
                continue

            docs_before = len(self.docs)
            for p in self.extract_from_html(text, url):
                enq(p)
            # JS-render fallback (colleague Extraction_Script) for SPA / KnowledgeCenter
            need_pw = self.looks_like_spa_shell(text, url) or (
                self.page_priority(url) == 0 and len(self.docs) == docs_before
            )
            if need_pw:
                for p in self.playwright_discover(url):
                    enq(p)

        # Always Playwright-pass remaining high-priority library seeds not fully scraped
        for seed in list(getattr(self, "_seed_pages", []))[:200]:
            if self.page_priority(seed) != 0:
                continue
            if self._pw_renders >= self._pw_max_renders:
                break
            if seed in self.visited_pages and any(
                k in (self.discovery_methods or {})
                for k in ("playwright_net", "playwright_html", "playwright_api")
            ):
                continue
            # re-render key library pages once more if few library docs
            if sum(
                1
                for d in self.docs.values()
                if "knowledge" in (d.get("url") or "").lower()
                or "mediacenter" in (d.get("url") or "").lower()
            ) < 100 and self.page_priority(seed) == 0:
                for p in self.playwright_discover(seed):
                    enq(p)

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
            "waf_blocks": self._waf_blocks,
            "playwright_renders": self._pw_renders,
            "hit_page_cap": self.pages_seen >= self.max_pages,
            "discovery_method_detail": (
                "nav_api + sitemap + SharePoint DataSources + priority BFS "
                "+ href/script/json + Playwright JS fallback (KnowledgeCenter)"
            ),
        }
        self.log(
            f"[discover] done pages={self.pages_seen} listed={len(self.docs)} "
            f"methods={self.discovery_methods} datasources={len(self.datasources_found)} "
            f"sitemaps={len(self.sitemaps_used)} playwright={self._pw_renders} waf={self._waf_blocks}"
        )
        # shutdown playwright
        try:
            if self._pw_browser is not None:
                self._pw_browser.close()
                self._pw_browser = None
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None
        except Exception:
            pass
        self.save_list(phase="listed", extra_stats=stats)
        self.publish_status(
            "listed",
            f"listed {len(self.docs)} documents on {self.root} (pages={self.pages_seen})",
            force_git=True,
        )
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
                self.publish_status(
                    "downloading",
                    f"downloading {i}/{total} for {self.label} "
                    f"(ok={ok} scanned={scanned} fail={fail})",
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
        for d in list(self.docs.values()):  # full list for Crawl tab
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

    def publish_status(self, phase: str, message: str, *, force_git: bool = False) -> None:
        """Write list + crawl_status and push so the public Crawl tab shows listed counts."""
        try:
            from live_publish import publish

            # Always refresh list file before publish so git stages latest discovery
            self.save_list(phase=phase)
            counts = self.status_counts()
            ministry_progress = {
                "label": self.label,
                "target_url": self.start_url,
                "counts": counts,
                "discovery_methods": dict(self.discovery_methods),
                "pages_visited": self.pages_seen,
                "sitemaps_used": list(self.sitemaps_used)[:20],
                "datasources_found": len(self.datasources_found),
                "list_file": "data/ministry_document_list.json",
                "updated_at": now_iso(),
            }
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
                    "pages_visited": self.pages_seen,
                },
                ministry_progress=ministry_progress,
                force_git=force_git,
                min_git_interval_sec=90.0,
            )
        except Exception as e:
            self.log(f"[publish] {e}")

    def run(self) -> dict:
        t0 = time.time()
        self.publish_status(
            "discovering",
            f"discovering documents on {self.start_url}",
            force_git=True,
        )
        dstats = self.discover()
        # discover() already force-publishes "listed"
        dl_stats = {}
        if self.do_download and self.docs:
            self.publish_status(
                "downloading",
                f"downloading {len(self.docs)} listed docs",
                force_git=True,
            )
            dl_stats = self.download_all()
            self.publish_status(
                "idle",
                (
                    f"{self.label}: listed={dl_stats.get('listed')} "
                    f"downloaded={dl_stats.get('downloaded')} "
                    f"scanned={dl_stats.get('scanned_pdf')} "
                    f"failed={dl_stats.get('download_failed')}"
                ),
                force_git=True,
            )
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
    ap.add_argument("--max-pages", type=int, default=2000)
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

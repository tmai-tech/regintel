#!/usr/bin/env python3
"""
Full-proof gazette / bill PDF extractor.

Discovery model (from colleague Extraction_Script.py):
  BFS same-site crawl of each source URL → find every .pdf → download.

  1. HTTP GET each page (fast)
  2. Auto Playwright fallback when the page is a JS shell / blocked / empty
  3. Queue every same-site HTML link (true site crawl, not 1-level only)
  4. Collect all PDF (document) links
  5. Download with resume, URL + content-hash dedupe

Sources:
  - data/gazette.json (Excel Gazette & Parliament Bills sheet)
  - --url / --from-file for ad-hoc / future test links

Usage:
  .venv/bin/python collector/download_gazette_pdfs.py --max-pages 500
  .venv/bin/python collector/download_gazette_pdfs.py --url-only \\
      --url "https://example.gov/bills" --label Example --max-pages 300
"""
from __future__ import annotations

import sys
from pathlib import Path as _PathForSys

sys.path.insert(0, str(_PathForSys(__file__).resolve().parent))
sys.path.insert(0, str(_PathForSys(__file__).resolve().parents[1]))

# UTF-8 stdout (colleague script reliability fix)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

import httpx

try:
    from collector.site_crawler import SiteCrawler, FoundDoc, DEFAULT_UA
    from collector import site_adapters
    from collector import live_publish
    from collector.pdf_relevance import (
        MINISTRY_LEGAL_SEED_PATHS,
        filter_regulatory_docs,
        is_regulatory_pdf,
        legal_seeds_for_url,
        regulatory_score,
    )
except ImportError:
    from site_crawler import SiteCrawler, FoundDoc, DEFAULT_UA  # type: ignore
    import site_adapters  # type: ignore
    import live_publish  # type: ignore
    from pdf_relevance import (  # type: ignore
        MINISTRY_LEGAL_SEED_PATHS,
        filter_regulatory_docs,
        is_regulatory_pdf,
        legal_seeds_for_url,
        regulatory_score,
    )

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GAZETTE_JSON = DATA / "gazette.json"
PDF_ROOT = DATA / "pdfs"
MANIFEST_PATH = PDF_ROOT / "manifest.json"
LOG_PATH = PDF_ROOT / "crawl_log.txt"

# Include Sitecore-style .pdf.aspx (SOCPA and many gov CMS sites)
PDF_EXT_RE = re.compile(r"\.pdf(\.aspx)?($|\?|#|;)", re.I)


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
        "source_reports": [],
        "stats": {},
    }


def save_manifest(manifest: dict) -> None:
    PDF_ROOT.mkdir(parents=True, exist_ok=True)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


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


def safe_filename(url: str, title: str = "") -> str:
    parsed = urlparse(url)
    name = unquote(Path(parsed.path).name or "document.pdf")
    name = name.split(";")[0]
    # Sitecore: exposure-draft....pdf.aspx → exposure-draft....pdf
    if name.lower().endswith(".aspx"):
        name = name[: -len(".aspx")]
    if not name.lower().endswith(".pdf"):
        # getattachment UUID paths sometimes omit .pdf in the last segment
        if ".pdf" in name.lower():
            pass
        else:
            name = name + ".pdf"
    name = re.sub(r"[^\w.\-()+ ]+", "_", name)
    name = name.strip(" ._") or "document.pdf"
    if len(name) > 140:
        stem = Path(name).stem[:100]
        name = f"{stem}_{content_hash(url.encode())}.pdf"
    if name.lower() in ("document.pdf", "file.pdf", "download.pdf", "pdf.pdf"):
        base = slugify(title)[:40] or content_hash(url.encode())
        name = f"{base}.pdf"
    return name


def load_url_file(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"URL file not found: {path}")
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if p.suffix.lower() == ".json" or raw.startswith("[") or raw.startswith("{"):
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("urls") or data.get("sources") or []
        out = []
        for item in data:
            if isinstance(item, str):
                out.append({"url": item, "jurisdiction": "AdHoc", "source_kind": "custom"})
            elif isinstance(item, dict) and item.get("url"):
                out.append(
                    {
                        "url": item["url"],
                        "jurisdiction": item.get("jurisdiction") or "AdHoc",
                        "source_kind": item.get("source_kind") or item.get("kind") or "custom",
                    }
                )
        return out
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) == 1:
            out.append({"url": parts[0], "jurisdiction": "AdHoc", "source_kind": "custom"})
        elif len(parts) == 2:
            out.append({"jurisdiction": parts[0], "url": parts[1], "source_kind": "custom"})
        else:
            out.append(
                {
                    "jurisdiction": parts[0],
                    "source_kind": parts[1] or "custom",
                    "url": parts[2],
                }
            )
    return out


class GazettePdfCollector:
    def __init__(
        self,
        *,
        max_pdfs_per_source: int = 0,
        max_pages: int = 500,
        delay: float = 0.4,
        include_legal_db: bool = False,
        jurisdictions: list[str] | None = None,
        dry_run: bool = False,
        timeout: float = 25.0,
        use_playwright: bool = True,
        extra_sources: list[dict] | None = None,
        skip_gazette: bool = False,
        live_publish_every: int = 5,
        time_budget_minutes: int = 0,
        git_push: bool | None = None,
        regulatory_only: bool = False,
        max_minutes_per_source: int = 0,
        skip_if_pdfs: int = 0,
    ):
        # 0 = unlimited PDFs per source
        self.max_pdfs_per_source = max_pdfs_per_source
        self.max_pages = max_pages
        self.delay = delay
        self.include_legal_db = include_legal_db
        self.jurisdictions = {j.lower() for j in jurisdictions} if jurisdictions else None
        self.dry_run = dry_run
        self.timeout = timeout
        self.use_playwright = use_playwright
        self.extra_sources = extra_sources or []
        self.skip_gazette = skip_gazette
        self.live_publish_every = max(0, live_publish_every)
        self.time_budget_minutes = max(0, time_budget_minutes)
        self.git_push = git_push
        # ministry / SA mode: only keep laws, regulations, decrees, circulars…
        self.regulatory_only = regulatory_only
        # Hard cap per ministry so all 21 links get a turn in one GHA run
        self.max_minutes_per_source = max(0, max_minutes_per_source)
        # Skip source if catalog already has this many PDFs for its jurisdiction
        self.skip_if_pdfs = max(0, skip_if_pdfs)
        self._started_at = time.time()
        self._source_deadline: float | None = None
        self._downloads_since_publish = 0
        self._stop_requested = False

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
                "User-Agent": DEFAULT_UA,
                "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            http2=False,
        )
        self.stats = {
            "sources_visited": 0,
            "pages_crawled": 0,
            "js_pages": 0,
            "pdfs_discovered": 0,
            "pdfs_downloaded": 0,
            "pdfs_skipped_existing": 0,
            "pdfs_capped": 0,
            "pdfs_rejected_junk": 0,
            "errors": 0,
        }
        self.source_reports: list[dict] = []
        PDF_ROOT.mkdir(parents=True, exist_ok=True)
        self._log_f = open(LOG_PATH, "a", encoding="utf-8")

    def log(self, msg: str) -> None:
        print(msg, flush=True)
        try:
            self._log_f.write(msg + "\n")
            self._log_f.flush()
        except Exception:
            pass

    def close(self) -> None:
        self.client.close()
        self.manifest["stats"] = self.stats
        save_manifest(self.manifest)
        # final publish so site shows latest count
        try:
            self._publish(
                phase="idle" if not self._stop_requested else "paused",
                message="crawl finished or paused",
                force_git=True,
            )
        except Exception as e:
            self.log(f"[live-publish] final publish error: {e}")
        try:
            self._log_f.close()
        except Exception:
            pass

    def budget_exceeded(self) -> bool:
        if self.time_budget_minutes > 0:
            if (time.time() - self._started_at) >= self.time_budget_minutes * 60:
                return True
        if self._source_deadline is not None and time.time() >= self._source_deadline:
            return True
        return False

    def source_time_exceeded(self) -> bool:
        return (
            self._source_deadline is not None and time.time() >= self._source_deadline
        )

    def _publish(
        self,
        *,
        phase: str = "running",
        message: str = "",
        current_source: dict | None = None,
        force_git: bool = False,
    ) -> None:
        if self.dry_run:
            return
        self.manifest["stats"] = self.stats
        save_manifest(self.manifest)
        try:
            live_publish.publish(
                phase=phase,
                message=message,
                current_source=current_source,
                git_push=self.git_push,
                force_git=force_git,
                min_git_interval_sec=120.0 if not force_git else 0.0,
            )
        except Exception as e:
            self.log(f"[live-publish] {e}")

    def _under_cap(self, n: int) -> bool:
        if self.max_pdfs_per_source <= 0:
            return True
        return n < self.max_pdfs_per_source

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
            self.log(f"  [dry-run] {url}")
            return rec

        headers = {}
        if source_page:
            headers["Referer"] = source_page
        if "parliament.uk" in url:
            headers["Referer"] = headers.get("Referer") or "https://bills.parliament.uk/"

        try:
            resp = self.client.get(url, headers=headers or None)
            body = resp.content
            status = resp.status_code
            ct = resp.headers.get("content-type", "")
        except Exception as e:
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {
                    "url": url,
                    "error": str(e)[:300],
                    "stage": "download_pdf",
                    "jurisdiction": jurisdiction,
                    "source_kind": source_kind,
                }
            )
            self.log(f"  [fail] {url} — {e}")
            return None

        time.sleep(self.delay)

        if status == 403:
            # one retry with browser-ish referer
            try:
                resp = self.client.get(
                    url,
                    headers={
                        "Referer": source_page or "https://www.google.com/",
                        "User-Agent": DEFAULT_UA,
                    },
                )
                body, status, ct = resp.content, resp.status_code, resp.headers.get("content-type", "")
            except Exception as e:
                body, status, ct = b"", 0, ""
                self.log(f"  [fail retry] {url} — {e}")
            time.sleep(self.delay)

        if not body:
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {
                    "url": url,
                    "error": "empty body",
                    "stage": "download_pdf",
                    "jurisdiction": jurisdiction,
                }
            )
            self.log(f"  [fail] {url} — empty")
            return None
        if status and status >= 400:
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {
                    "url": url,
                    "error": f"HTTP {status}",
                    "stage": "download_pdf",
                    "jurisdiction": jurisdiction,
                }
            )
            self.log(f"  [http {status}] {url}")
            return None
        if not body.startswith(b"%PDF") and "pdf" not in (ct or "").lower() and not PDF_EXT_RE.search(url):
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {
                    "url": url,
                    "error": f"not a PDF (ct={ct})",
                    "stage": "download_pdf",
                    "jurisdiction": jurisdiction,
                }
            )
            self.log(f"  [skip not-pdf] {url} ct={ct}")
            return None
        if not body.startswith(b"%PDF") and "pdf" in (ct or "").lower():
            # some servers lie; still require magic when possible
            pass
        if not body.startswith(b"%PDF"):
            self.stats["errors"] += 1
            self.manifest.setdefault("errors", []).append(
                {
                    "url": url,
                    "error": f"missing %PDF magic (ct={ct})",
                    "stage": "download_pdf",
                    "jurisdiction": jurisdiction,
                }
            )
            self.log(f"  [skip not-pdf magic] {url}")
            return None

        sha = content_hash(body)
        if sha in self._file_hashes:
            self.stats["pdfs_skipped_existing"] += 1
            self._downloaded_urls.add(url)  # don't retry this URL
            self.log(f"  [dup hash] {url}")
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
        self.log(f"  [ok] {dest.name} ({len(body)} bytes) ← {url[:120]}")
        # Live site: refresh catalog ASAP so new PDFs appear on GitHub Pages
        self._downloads_since_publish += 1
        if self.live_publish_every and self._downloads_since_publish >= self.live_publish_every:
            self._downloads_since_publish = 0
            self._publish(
                phase="running",
                message=f"downloaded {self.stats['pdfs_downloaded']} new this run",
                current_source={
                    "jurisdiction": jurisdiction,
                    "source_kind": source_kind,
                    "url": source_page,
                },
            )
        return rec

    def process_source_page(
        self,
        *,
        page_url: str,
        jurisdiction: str,
        source_kind: str,
    ) -> None:
        self.log(f"\n==> [{jurisdiction}] {source_kind}: {page_url}")
        self.stats["sources_visited"] += 1
        report = {
            "jurisdiction": jurisdiction,
            "source_kind": source_kind,
            "source_url": page_url,
            "pages_crawled": 0,
            "js_pages": 0,
            "pdfs_candidates": 0,
            "pdfs_regulatory": 0,
            "pdfs_rejected_junk": 0,
            "pdfs_downloaded": 0,
            "error": None,
        }
        self._publish(
            phase="running",
            message=f"crawling {jurisdiction} / {source_kind}",
            current_source={
                "jurisdiction": jurisdiction,
                "source_kind": source_kind,
                "url": page_url,
            },
        )

        reg_focus = self.regulatory_only or source_kind == "ministry"
        if self.max_minutes_per_source > 0:
            self._source_deadline = time.time() + self.max_minutes_per_source * 60
            self.log(
                f"  [cap] max {self.max_minutes_per_source} min for this source "
                f"(so remaining ministries still get a turn)"
            )
        else:
            self._source_deadline = None

        crawler = SiteCrawler(
            max_pages=self.max_pages,
            delay=self.delay,
            timeout=min(self.timeout, 12.0) if reg_focus else self.timeout,
            pdf_only=True,
            use_playwright=self.use_playwright,
            same_site_only=True,
            log=self.log,
            extra_seed_paths=legal_seeds_for_url(page_url) if reg_focus else None,
            regulatory_focus=reg_focus,
            should_stop=lambda: self.budget_exceeded() or self.source_time_exceeded(),
        )
        crawl = crawler.crawl(page_url)
        # clear per-source deadline after BFS (downloads may still run briefly)
        source_over = self.source_time_exceeded()
        report["pages_crawled"] = crawl.pages_visited
        report["js_pages"] = crawl.js_pages
        self.stats["pages_crawled"] += crawl.pages_visited
        self.stats["js_pages"] += crawl.js_pages

        # Merge site-specific API discoveries (FR, UK Bills, …) as extras
        extra_docs: list[FoundDoc] = []
        try:
            # lightweight fetch adapter for site_adapters
            def _fetch(url, extra_headers=None):
                try:
                    r = self.client.get(url, headers=extra_headers or None)
                    return r.status_code, r.headers.get("content-type", ""), r.content, None
                except Exception as e:
                    return None, None, None, str(e)[:240]

            def _extract_links(base, html):
                # minimal adapter bridge
                from bs4 import BeautifulSoup
                from urllib.parse import urljoin

                soup = BeautifulSoup(html, "lxml")
                out = []
                for a in soup.find_all("a", href=True):
                    full = urljoin(base, a["href"]).split("#")[0]
                    out.append(
                        {
                            "url": full,
                            "text": a.get_text(" ", strip=True)[:300],
                            "is_pdf": ".pdf" in full.lower(),
                        }
                    )
                return out

            def _looks_bill(u, t=""):
                blob = f"{u} {t}".lower()
                return any(
                    k in blob
                    for k in (
                        "bill",
                        "amend",
                        "act",
                        "law",
                        "gazette",
                        "regulation",
                        "statut",
                        "pdf",
                    )
                )

            extras = site_adapters.discover_extra_pdfs(
                page_url,
                fetch=_fetch,
                delay=self.delay,
                extract_links=_extract_links,
                looks_like_bill=_looks_bill,
            )
            for e in extras:
                if e.get("is_pdf") or PDF_EXT_RE.search(e.get("url") or ""):
                    extra_docs.append(
                        FoundDoc(
                            url=e["url"],
                            text=e.get("text") or "",
                            source_page=page_url,
                            is_pdf=True,
                        )
                    )
            if extra_docs:
                self.log(f"  site-specific API extras: {len(extra_docs)}")
        except Exception as e:
            self.log(f"  [site-adapter warn] {e}")

        # Merge + dedupe docs (crawl first, then API extras)
        by_url: dict[str, FoundDoc] = {}
        for d in list(crawl.docs) + extra_docs:
            if not d.url:
                continue
            if d.url not in by_url:
                by_url[d.url] = d
        docs = list(by_url.values())
        # Prefer PDFs
        docs = [d for d in docs if d.is_pdf or PDF_EXT_RE.search(d.url)]
        report["pdfs_candidates"] = len(docs)

        reg_focus = self.regulatory_only or source_kind == "ministry"
        if reg_focus and docs:
            keep, rejected = filter_regulatory_docs(docs, min_score=15)
            report["pdfs_rejected_junk"] = len(rejected)
            report["pdfs_regulatory"] = len(keep)
            self.stats["pdfs_rejected_junk"] = self.stats.get("pdfs_rejected_junk", 0) + len(
                rejected
            )
            self.log(
                f"  regulatory filter: keep {len(keep)} / reject {len(rejected)} "
                f"(of {len(docs)} PDFs) — dropping IoT/news/workshop junk"
            )
            if rejected and len(rejected) <= 8:
                for d, sc in rejected[:8]:
                    self.log(f"    [junk score={sc}] {(d.text or d.url)[:90]}")
            elif rejected:
                for d, sc in rejected[:5]:
                    self.log(f"    [junk score={sc}] {(d.text or d.url)[:90]}")
                self.log(f"    … +{len(rejected) - 5} more rejected")
            docs = keep

        self.log(
            f"  downloading from {len(docs)} PDF candidates "
            f"(crawled {crawl.pages_visited} pages, cap="
            f"{self.max_pdfs_per_source or '∞'})"
        )

        downloaded_here = 0
        attempts = 0
        max_attempts = (
            self.max_pdfs_per_source * 3
            if self.max_pdfs_per_source > 0
            else max(len(docs), 1)
        )

        for d in docs:
            if self.source_time_exceeded():
                self.log("  [source-cap] time up for this ministry — moving on")
                break
            if self.time_budget_minutes > 0 and (
                time.time() - self._started_at
            ) >= self.time_budget_minutes * 60:
                self._stop_requested = True
                self.log("  [time-budget] stopping downloads for this run")
                break
            if not self._under_cap(downloaded_here):
                self.stats["pdfs_capped"] += len(docs) - attempts
                self.log(
                    f"  [cap] {downloaded_here} new PDFs "
                    f"({len(docs) - attempts}+ not attempted)"
                )
                break
            if attempts >= max_attempts:
                break
            rec = self.download_pdf(
                url=d.url,
                jurisdiction=jurisdiction,
                source_kind=source_kind,
                source_page=d.source_page or page_url,
                title=d.text or d.url,
            )
            attempts += 1
            if rec:
                downloaded_here += 1
            # flush often so crash never loses much (colleague SAVE_EVERY pattern)
            if attempts % 10 == 0:
                save_manifest(self.manifest)

        report["pdfs_downloaded"] = downloaded_here
        if source_over or self.source_time_exceeded():
            report["error"] = report.get("error") or "source_time_cap"
        if crawl.empty_streak_warning:
            report["error"] = "possible_rate_limit"
        if crawl.errors and not docs:
            report["error"] = crawl.errors[0][:200]
        self.source_reports.append(report)
        self._source_deadline = None
        self.log(
            f"  source result: {downloaded_here} new / "
            f"{attempts} attempts / {len(docs)} candidates"
        )
        save_manifest(self.manifest)
        # After each source: publish so site updates
        self._publish(
            phase="running",
            message=f"finished {jurisdiction} / {source_kind}: +{downloaded_here} PDFs",
            current_source={
                "jurisdiction": jurisdiction,
                "source_kind": source_kind,
                "url": page_url,
                "pdfs_downloaded": downloaded_here,
                "pdfs_candidates": len(docs),
            },
            force_git=True,
        )

    def _crawl_source(self, *, url: str, jurisdiction: str, source_kind: str) -> None:
        try:
            self.process_source_page(
                page_url=url, jurisdiction=jurisdiction, source_kind=source_kind
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
            self.log(f"  [exception] {e}")
        save_manifest(self.manifest)

    def run(self) -> None:
        self._publish(phase="starting", message="crawl starting", force_git=True)

        # Ministry / --from-file list: visit authorities with fewest PDFs first so a
        # long BFS on e.g. MOMAH does not starve the rest of the morning link list.
        extras = list(self.extra_sources or [])
        if extras and self.skip_gazette:
            from collections import Counter

            already = Counter(
                str(d.get("jurisdiction") or "")
                for d in (self.manifest.get("downloads") or [])
                if not d.get("dry_run")
            )
            extras = sorted(
                extras,
                key=lambda e: (
                    already.get(str(e.get("jurisdiction") or ""), 0),
                    str(e.get("jurisdiction") or ""),
                ),
            )
            order = [
                f"{e.get('jurisdiction')}({already.get(str(e.get('jurisdiction') or ''), 0)})"
                for e in extras
            ]
            self.log(
                f"[priority] crawling {len(extras)} list URLs, fewest PDFs first: "
                + ", ".join(order[:12])
                + ("…" if len(order) > 12 else "")
            )

        from collections import Counter as _Counter

        already_counts = _Counter(
            str(d.get("jurisdiction") or "")
            for d in (self.manifest.get("downloads") or [])
            if not d.get("dry_run")
        )
        visited_ok = 0
        skipped_done = 0
        for extra in extras:
            # Only stop the whole run on GLOBAL time budget — not per-source cap
            if self.time_budget_minutes > 0 and (
                time.time() - self._started_at
            ) >= self.time_budget_minutes * 60:
                self._stop_requested = True
                self.log("[time-budget] exceeded — pausing (resume-safe next run)")
                break
            url = (extra.get("url") or "").strip()
            if not url:
                continue
            if not url.startswith("http"):
                url = "https://" + url.lstrip("/")
            jur = extra.get("jurisdiction") or "AdHoc"
            if self.skip_if_pdfs > 0 and already_counts.get(jur, 0) >= self.skip_if_pdfs:
                skipped_done += 1
                self.log(
                    f"\n==> [skip] {jur}: already have {already_counts[jur]} PDFs "
                    f"(skip_if_pdfs={self.skip_if_pdfs}) — covering other ministries first"
                )
                continue
            self._crawl_source(
                url=url,
                jurisdiction=jur,
                source_kind=extra.get("source_kind") or "custom",
            )
            visited_ok += 1
            # refresh count after crawl
            already_counts = _Counter(
                str(d.get("jurisdiction") or "")
                for d in (self.manifest.get("downloads") or [])
                if not d.get("dry_run")
            )
        if extras:
            self.log(
                f"[list] visited {visited_ok}/{len(extras)} sources "
                f"(skipped already-covered: {skipped_done})"
            )

        if not self.skip_gazette and not self._stop_requested:
            for row in load_gazette():
                if self.budget_exceeded():
                    self._stop_requested = True
                    self.log("[time-budget] exceeded — pausing (resume-safe next run)")
                    break
                jurisdiction = row.get("jurisdiction") or "Unknown"
                if self.jurisdictions and jurisdiction.lower() not in self.jurisdictions:
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
                    if self.budget_exceeded():
                        self._stop_requested = True
                        break
                    self._crawl_source(url=url, jurisdiction=jurisdiction, source_kind=kind)

        self.manifest["source_reports"] = (
            (self.manifest.get("source_reports") or []) + self.source_reports
        )[-500:]
        save_manifest(self.manifest)

        self.log("\n===== SUMMARY =====")
        self.log(json.dumps(self.stats, indent=2))
        total = len(self.manifest.get("downloads") or [])
        self.log(f"Total PDFs on disk (manifest): {total}")
        self.log(f"Manifest: {MANIFEST_PATH}")
        self.log(f"Log: {LOG_PATH}")


def main():
    p = argparse.ArgumentParser(
        description=(
            "Full-site BFS PDF extractor (colleague Extraction_Script strategy). "
            "Crawls each source URL across the site, finds PDFs, downloads them."
        )
    )
    p.add_argument("--jurisdiction", action="append", dest="jurisdictions")
    p.add_argument("--url", action="append", dest="urls", help="Ad-hoc URL to crawl (repeatable)")
    p.add_argument("--from-file", dest="url_file", help="File of extra URLs")
    p.add_argument("--label", default="AdHoc", help="Label for --url targets")
    p.add_argument("--kind", default="custom", help="source_kind for --url targets")
    p.add_argument("--url-only", action="store_true", help="Only --url / --from-file")
    p.add_argument(
        "--max-pdfs-per-source",
        type=int,
        default=0,
        help="Max NEW PDFs to download per source URL (0=unlimited, default)",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Max HTML pages to BFS-crawl per source URL (default 500; "
        "colleague script uses 2000)",
    )
    p.add_argument("--delay", type=float, default=0.4, help="Seconds between requests")
    p.add_argument("--include-legal-db", action="store_true")
    p.add_argument(
        "--no-playwright",
        action="store_true",
        help="Disable JS-rendering fallback",
    )
    p.add_argument("--playwright", action="store_true", help="(default on) force enable")
    p.add_argument("--dry-run", action="store_true", help="Discover only, no download")
    p.add_argument("--timeout", type=float, default=25.0)
    p.add_argument(
        "--live-publish-every",
        type=int,
        default=5,
        help="Refresh web catalog/status every N new PDF downloads (0=only per source)",
    )
    p.add_argument(
        "--time-budget-minutes",
        type=int,
        default=0,
        help="Stop after N minutes (resume-safe). Use ~300 on GitHub Actions (6h job).",
    )
    p.add_argument(
        "--git-push",
        action="store_true",
        help="Commit+push catalog/status/manifest for live GitHub Pages",
    )
    p.add_argument(
        "--no-git-push",
        action="store_true",
        help="Never git push even on GITHUB_ACTIONS",
    )
    p.add_argument(
        "--regulatory-only",
        action="store_true",
        help="Only download law/regulation/decree/circular PDFs; skip IoT, "
        "workshops, newsletters, marketing (recommended for ministry crawls)",
    )
    p.add_argument(
        "--max-minutes-per-source",
        type=int,
        default=0,
        help="Hard time cap per ministry/source (minutes). "
        "Ensures all list URLs get a turn (e.g. 8 for 21 Saudi links).",
    )
    p.add_argument(
        "--skip-if-pdfs",
        type=int,
        default=0,
        help="Skip a jurisdiction if it already has this many PDFs in the "
        "manifest (0=never skip). Use e.g. 8 so empty ministries are filled first.",
    )
    # backwards-compat aliases (ignored or mapped)
    p.add_argument("--max-follow-pages", type=int, default=None, help=argparse.SUPPRESS)
    p.add_argument("--max-list-pages", type=int, default=None, help=argparse.SUPPRESS)
    args = p.parse_args()

    # Map old flags: if user set max-follow-pages high, bump max_pages
    max_pages = args.max_pages
    if args.max_follow_pages and args.max_follow_pages > max_pages:
        max_pages = args.max_follow_pages

    extra: list[dict] = []
    for u in args.urls or []:
        extra.append({"url": u, "jurisdiction": args.label, "source_kind": args.kind})
    if args.url_file:
        extra.extend(load_url_file(args.url_file))
    if args.url_only and not extra:
        raise SystemExit("--url-only requires --url or --from-file")

    use_pw = not args.no_playwright
    git_push: bool | None
    if args.no_git_push:
        git_push = False
    elif args.git_push:
        git_push = True
    else:
        git_push = None  # auto on GITHUB_ACTIONS

    # Ministry / --url-only lists default to regulatory filter (laws not IoT junk)
    regulatory_only = bool(args.regulatory_only or args.url_only)

    # For ministry lists: default 8 min/source + skip if already has 5 PDFs
    max_min_src = args.max_minutes_per_source
    skip_if = args.skip_if_pdfs
    if args.url_only:
        if max_min_src <= 0:
            max_min_src = 8
        if skip_if <= 0:
            skip_if = 5

    collector = GazettePdfCollector(
        max_pdfs_per_source=args.max_pdfs_per_source,
        max_pages=max_pages,
        delay=args.delay,
        include_legal_db=args.include_legal_db,
        jurisdictions=args.jurisdictions,
        dry_run=args.dry_run,
        timeout=args.timeout,
        use_playwright=use_pw,
        extra_sources=extra,
        skip_gazette=args.url_only,
        live_publish_every=args.live_publish_every,
        time_budget_minutes=args.time_budget_minutes,
        git_push=git_push,
        regulatory_only=regulatory_only,
        max_minutes_per_source=max_min_src,
        skip_if_pdfs=skip_if,
    )
    try:
        collector.run()
    finally:
        collector.close()


if __name__ == "__main__":
    main()

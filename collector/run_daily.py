#!/usr/bin/env python3
"""Daily collector: fetch due primary sources and record change candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WEB_DATA = ROOT / "web" / "data"
UA = "BCI-RegIntel/1.0 (+https://github.com/tmai-tech/regintel; regulatory-monitoring)"


def load_json(name: str, default=None):
    path = DATA / name
    if not path.exists():
        return default if default is not None else []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(name: str, obj):
    DATA.mkdir(exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    (DATA / name).write_text(text, encoding="utf-8")
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / name).write_text(text, encoding="utf-8")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def extract_items(base_url: str, html: str, limit: int = 25) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen = set()
    # Prefer article/news links
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text or len(text) < 12 or len(text) > 220:
            continue
        low = href.lower()
        if low.startswith(("javascript:", "mailto:", "#", "tel:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        # skip pure nav
        nav_words = ("login", "cookie", "privacy policy", "contact us", "home", "skip to")
        if text.lower() in nav_words:
            continue
        key = full.split("#")[0]
        if key in seen:
            continue
        # score: path looks like news/update
        path = parsed.path.lower()
        score = 0
        for kw in ("news", "press", "update", "circular", "consultation", "bulletin", "release", "gazette", "bill", "regulation", "notice"):
            if kw in path or kw in text.lower():
                score += 1
        if score == 0 and not re.search(r"/\d{4}/", path):
            continue
        seen.add(key)
        items.append({"title": text, "url": key, "score": score})
        if len(items) >= limit * 3:
            break
    items.sort(key=lambda x: -x["score"])
    return [{"title": i["title"], "url": i["url"]} for i in items[:limit]]


def should_run(source: dict, force: bool) -> bool:
    if force:
        return True
    if source.get("status") not in (None, "active"):
        return False
    freq = (source.get("frequency") or "").lower()
    # Always include Frequent / Most Frequent / empty as daily-ish
    if "less" in freq:
        # run less frequent sources only on even day-of-year
        return datetime.now(timezone.utc).timetuple().tm_yday % 2 == 0
    return True


def run(limit: int, force: bool, regions: list[str] | None):
    primary = load_json("primary_sources.json", [])
    updates = load_json("updates.json", [])
    seen = load_json("seen_items.json", {})
    runs = load_json("fetch_runs.json", [])

    # filter
    candidates = [s for s in primary if s.get("url") and should_run(s, force)]
    if regions:
        regions_l = {r.lower() for r in regions}
        candidates = [s for s in candidates if (s.get("region") or "").lower() in regions_l]

    # prioritize known high-value jurisdictions
    priority = ("canada", "uk", "us - federal", "new york", "british columbia", "european", "india", "australia")
    def rank(s):
        j = (s.get("jurisdiction") or "").lower()
        for i, p in enumerate(priority):
            if p in j:
                return i
        return 50

    candidates.sort(key=rank)
    if limit:
        candidates = candidates[:limit]

    now = datetime.now(timezone.utc).isoformat()
    new_updates = []
    ok = fail = 0

    timeout = httpx.Timeout(25.0, connect=10.0)
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        for idx, src in enumerate(candidates, 1):
            url = src["url"]
            if not str(url).startswith("http"):
                url = "https://" + str(url).lstrip("/")
            run_rec = {
                "source_url": url,
                "jurisdiction": src.get("jurisdiction"),
                "authority": src.get("authority"),
                "started_at": now,
                "status": "error",
            }
            try:
                resp = client.get(url)
                body = resp.text or ""
                ch = content_hash(body)
                items = extract_items(str(resp.url), body)
                run_rec.update(
                    {
                        "http_status": resp.status_code,
                        "content_hash": ch,
                        "item_count": len(items),
                        "status": "ok" if resp.status_code < 400 else "http_error",
                    }
                )
                if resp.status_code >= 400:
                    fail += 1
                else:
                    ok += 1
                    src_key = content_hash(url)
                    prev = seen.get(src_key, {"urls": [], "page_hash": None})
                    prev_urls = set(prev.get("urls") or [])
                    page_hash = prev.get("page_hash")
                    added = 0
                    for it in items:
                        if it["url"] in prev_urls:
                            continue
                        prev_urls.add(it["url"])
                        u = {
                            "id": content_hash(it["url"] + now),
                            "discovered_at": now,
                            "country": src.get("jurisdiction"),
                            "region": src.get("region"),
                            "authority": src.get("authority"),
                            "law_area": src.get("segment"),
                            "topical_relevance": ", ".join(src.get("topics") or [])[:200],
                            "title": it["title"],
                            "link": it["url"],
                            "source_url": url,
                            "relevancy": "Pending",
                            "alert_status": "new",
                            "tracked_by": "collector",
                        }
                        new_updates.append(u)
                        added += 1
                    # page-level change with no extractable items
                    if not items and page_hash and page_hash != ch:
                        new_updates.append(
                            {
                                "id": content_hash(url + ch + now),
                                "discovered_at": now,
                                "country": src.get("jurisdiction"),
                                "region": src.get("region"),
                                "authority": src.get("authority"),
                                "law_area": src.get("segment"),
                                "topical_relevance": ", ".join(src.get("topics") or [])[:200],
                                "title": f"Page content changed — {src.get('authority')}",
                                "link": url,
                                "source_url": url,
                                "relevancy": "Pending",
                                "alert_status": "new",
                                "tracked_by": "collector",
                            }
                        )
                        added += 1
                    # first successful snapshot: seed seen without flooding updates
                    if page_hash is None and not prev_urls and items:
                        # first run: record seen, only keep top 3 as sample updates if force seed
                        for it in items[:3]:
                            if it["url"] not in {u["link"] for u in new_updates}:
                                new_updates.append(
                                    {
                                        "id": content_hash(it["url"] + "seed" + now),
                                        "discovered_at": now,
                                        "country": src.get("jurisdiction"),
                                        "region": src.get("region"),
                                        "authority": src.get("authority"),
                                        "law_area": src.get("segment"),
                                        "topical_relevance": ", ".join(src.get("topics") or [])[:200],
                                        "title": it["title"],
                                        "link": it["url"],
                                        "source_url": url,
                                        "relevancy": "Pending",
                                        "alert_status": "seed",
                                        "tracked_by": "collector",
                                    }
                                )
                        prev_urls = {it["url"] for it in items}
                    seen[src_key] = {"urls": list(prev_urls)[-200:], "page_hash": ch, "last_ok": now}
                    run_rec["new_items"] = added
            except Exception as e:
                fail += 1
                run_rec["error"] = str(e)[:300]
            runs.append(run_rec)
            print(f"[{idx}/{len(candidates)}] {run_rec.get('status')} {src.get('jurisdiction')} — {src.get('authority')}")
            time.sleep(0.4)

    # prepend new updates
    all_updates = new_updates + updates
    # dedupe by link
    dedup = []
    seen_links = set()
    for u in all_updates:
        link = u.get("link")
        if link in seen_links:
            continue
        seen_links.add(link)
        dedup.append(u)
    dedup = dedup[:5000]

    save_json("updates.json", dedup)
    save_json("seen_items.json", seen)
    save_json("fetch_runs.json", runs[-2000:])

    meta = load_json("meta.json", {})
    meta["last_collector_run"] = now
    meta["last_collector_stats"] = {
        "sources_attempted": len(candidates),
        "ok": ok,
        "fail": fail,
        "new_updates": len(new_updates),
        "total_updates": len(dedup),
    }
    if "counts" not in meta:
        meta["counts"] = {}
    meta["counts"]["updates"] = len(dedup)
    save_json("meta.json", meta)

    # Rebuild enriched laws catalog for web / Android / Firestore
    try:
        import subprocess
        import sys

        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "build_laws_catalog.py")],
            cwd=str(ROOT),
        )
        laws_path = DATA / "laws_catalog.json"
        if laws_path.exists():
            laws = json.loads(laws_path.read_text(encoding="utf-8"))
            meta["counts"]["laws"] = len(laws)
            save_json("meta.json", meta)
    except Exception as e:
        print(f"laws catalog rebuild skipped: {e}")

    print(json.dumps(meta["last_collector_stats"], indent=2))


def main():
    p = argparse.ArgumentParser(description="BCI RegIntel daily collector")
    p.add_argument("--limit", type=int, default=40, help="Max sources to fetch this run")
    p.add_argument("--force", action="store_true")
    p.add_argument("--region", action="append", dest="regions", help="Filter by region (repeatable)")
    args = p.parse_args()
    run(limit=args.limit, force=args.force, regions=args.regions)


if __name__ == "__main__":
    main()

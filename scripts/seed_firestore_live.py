#!/usr/bin/env python3
"""Seed regintel_sites + regintel_crawls from the current catalog / active_crawls."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT / "scripts"))

from firestore_live import upsert_crawl_job, upsert_sites  # type: ignore
from saudi_ministry_allowlist import AUTHORITIES, site_code_for  # type: ignore


def main() -> None:
    catalog_path = ROOT / "web" / "data" / "pdfs_catalog.json"
    counts: Counter[str] = Counter()
    if catalog_path.exists():
        rows = json.loads(catalog_path.read_text(encoding="utf-8"))
        for r in rows:
            code = site_code_for(r)
            if code:
                counts[code] += 1

    sites = []
    for a in AUTHORITIES:
        code = a["code"]
        sites.append(
            {
                "code": code,
                "name": a.get("name") or code,
                "url": a.get("crawl_url") or a.get("url") or "",
                "label": a.get("label") or f"Saudi Arabia - {code}",
                "pdf_count": int(counts.get(code, 0)),
            }
        )
    n = upsert_sites(sites)
    print(f"sites={n} catalog_codes={dict(counts)}")

    crawls = ROOT / "web" / "data" / "active_crawls.json"
    jobs = []
    if crawls.exists():
        data = json.loads(crawls.read_text(encoding="utf-8"))
        jobs = data.get("jobs") or []
    ok = 0
    for j in jobs:
        if upsert_crawl_job(j):
            ok += 1
    print(f"crawls_upserted={ok}")


if __name__ == "__main__":
    main()

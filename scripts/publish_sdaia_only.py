#!/usr/bin/env python3
"""Filter published web catalogs to SDAIA-only (no Manitoba/global gazette)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "data"


def is_sdaia(p: dict) -> bool:
    j = str(p.get("jurisdiction") or "")
    h = str(p.get("host") or "")
    u = str(p.get("url") or p.get("open_url") or "")
    return "SDAIA" in j or "sdaia" in h.lower() or "sdaia" in u.lower()


def main() -> None:
    cat_path = WEB / "pdfs_catalog.json"
    pdfs = json.loads(cat_path.read_text(encoding="utf-8"))
    if not isinstance(pdfs, list):
        pdfs = pdfs.get("pdfs") or []
    sda = []
    for p in pdfs:
        if not is_sdaia(p):
            continue
        p = dict(p)
        p["jurisdiction"] = "Saudi Arabia - SDAIA"
        p["source_kind"] = p.get("source_kind") or "ministry"
        sda.append(p)
    cat_path.write_text(json.dumps(sda, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assets = ROOT / "android" / "app" / "src" / "main" / "assets" / "pdfs_catalog.json"
    if assets.parent.is_dir():
        assets.write_text(cat_path.read_text(encoding="utf-8"), encoding="utf-8")

    mins = [
        {
            "code": "SDAIA",
            "name": "Saudi Data and Artificial Intelligence Authority (SDAIA)",
            "url": "https://sdaia.gov.sa",
            "country": "Saudi Arabia",
            "authority_type": "Authority",
        }
    ]
    (WEB / "saudi_ministries.json").write_text(
        json.dumps(mins, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "data" / "saudi_ministries.json").write_text(
        json.dumps(mins, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (WEB / "laws_catalog.json").write_text("[]\n", encoding="utf-8")

    st = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "idle",
        "message": f"SDAIA-only site · {len(sda)} PDFs",
        "totals": {
            "pdfs": len(sda),
            "errors": 0,
            "source_reports": 0,
            "jurisdictions": 1,
        },
        "by_jurisdiction": [{"jurisdiction": "Saudi Arabia - SDAIA", "count": len(sda)}],
        "by_source_kind": [{"source_kind": "ministry", "count": len(sda)}],
        "current_source": {
            "jurisdiction": "Saudi Arabia - SDAIA",
            "url": "https://sdaia.gov.sa",
            "source_kind": "ministry",
        },
        "recent_pdfs": [],
        "last_source_reports": [],
        "stats": {},
    }
    mdl_path = WEB / "ministry_document_list.json"
    if mdl_path.exists():
        try:
            mdl = json.loads(mdl_path.read_text(encoding="utf-8"))
            st["ministry_document_list"] = {
                "label": mdl.get("label") or "Saudi Arabia - SDAIA",
                "target_url": mdl.get("target_url") or "https://sdaia.gov.sa",
                "counts": mdl.get("counts"),
                "discovery_methods": mdl.get("discovery_methods"),
                "pages_visited": mdl.get("pages_visited"),
                "list_file": "data/ministry_document_list.json",
                "updated_at": mdl.get("updated_at"),
            }
            c = mdl.get("counts") or {}
            st["totals"]["ministry_listed"] = c.get("listed_total", 0)
            st["totals"]["ministry_downloaded"] = c.get("downloaded", 0)
            st["totals"]["ministry_failed"] = c.get("download_failed", 0)
            st["totals"]["ministry_scanned"] = c.get("scanned_pdf", 0)
            st["totals"]["ministry_to_download"] = c.get("to_download", 0)
        except Exception:
            pass
    (WEB / "crawl_status.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"SDAIA-only publish: {len(sda)} PDFs")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Filter published web catalogs to SDAIA-only (no global gazette / multi-ministry)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "data"

# Files that are global collector noise — empty them on the public site.
EMPTY_LIST_FILES = (
    "laws_catalog.json",
    "primary_sources.json",
    "secondary_sources.json",
    "updates.json",
    "tracking.json",
    "gazette.json",
    "fetch_runs.json",
    "detailed_plan.json",
    "summary_plan.json",
    "seen_items.json",
    "pdfs_coverage.json",
)


def is_sdaia(p: dict) -> bool:
    j = str(p.get("jurisdiction") or "")
    h = str(p.get("host") or "")
    u = str(p.get("url") or p.get("open_url") or "")
    sp = str(p.get("source_page") or "")
    return (
        "SDAIA" in j
        or "sdaia" in h.lower()
        or "sdaia" in u.lower()
        or "sdaia" in sp.lower()
    )


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    WEB.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    cat_path = WEB / "pdfs_catalog.json"
    if cat_path.exists():
        pdfs = json.loads(cat_path.read_text(encoding="utf-8"))
        if not isinstance(pdfs, list):
            pdfs = pdfs.get("pdfs") or []
    else:
        pdfs = []
    sda = []
    for p in pdfs:
        if not is_sdaia(p):
            continue
        p = dict(p)
        p["jurisdiction"] = "Saudi Arabia - SDAIA"
        p["source_kind"] = p.get("source_kind") or "ministry"
        sda.append(p)
    _write(cat_path, sda)
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
    _write(WEB / "saudi_ministries.json", mins)
    _write(ROOT / "data" / "saudi_ministries.json", mins)

    # Strip global collector / multi-jurisdiction payloads from the public site
    for name in EMPTY_LIST_FILES:
        p = WEB / name
        if name == "seen_items.json":
            _write(p, {})
        else:
            _write(p, [])

    # Meta bar / collector totals — SDAIA only (no catalogue total / laws count)
    _write(
        WEB / "meta.json",
        {
            "generated_at": now,
            "site_scope": "SDAIA",
            "counts": {
                "sdaia_pdfs": len(sda),
                "jurisdictions": 1,
            },
            "message": f"SDAIA-only · {len(sda)} PDFs",
        },
    )

    # Eva corpus — keep only SDAIA summaries
    eva_path = WEB / "eva_summaries.json"
    eva_n = 0
    if eva_path.exists():
        try:
            eva = json.loads(eva_path.read_text(encoding="utf-8"))
            if isinstance(eva, list):
                eva_sda = [e for e in eva if isinstance(e, dict) and is_sdaia(e)]
                for e in eva_sda:
                    e["jurisdiction"] = "Saudi Arabia - SDAIA"
                _write(eva_path, eva_sda)
                eva_n = len(eva_sda)
            else:
                _write(eva_path, [])
        except Exception:
            _write(eva_path, [])
    else:
        _write(eva_path, [])

    _write(
        WEB / "eva_meta.json",
        {
            "updated_at": now,
            "count": eva_n,
            "total_indexed": eva_n,
            "site_scope": "SDAIA",
            "llm_available": False,
        },
    )

    st = {
        "updated_at": now,
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
            # Keep document list only if it is SDAIA-related
            label = str(mdl.get("label") or "")
            target = str(mdl.get("target_url") or "")
            if "sdaia" in label.lower() or "sdaia" in target.lower() or not label:
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
            else:
                # Non-SDAIA list — drop from public crawl status
                _write(mdl_path, {"documents": [], "counts": {}, "label": "Saudi Arabia - SDAIA"})
        except Exception:
            pass
    _write(WEB / "crawl_status.json", st)
    print(f"SDAIA-only publish: {len(sda)} PDFs, {eva_n} Eva summaries")


if __name__ == "__main__":
    main()

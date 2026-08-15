#!/usr/bin/env python3
"""Filter public web data to the 4 Saudi ministries (SDAIA, TGA, MC, MEWA)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from saudi_ministry_allowlist import (  # noqa: E402
    AUTHORITIES,
    is_allowed_ministry_row,
    normalize_jurisdiction,
)

WEB = ROOT / "web" / "data"

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

    kept = []
    for p in pdfs:
        if not is_allowed_ministry_row(p):
            continue
        p = dict(p)
        p["jurisdiction"] = normalize_jurisdiction(p)
        p["source_kind"] = p.get("source_kind") or "ministry"
        kept.append(p)
    _write(cat_path, kept)

    assets = ROOT / "android" / "app" / "src" / "main" / "assets" / "pdfs_catalog.json"
    if assets.parent.is_dir():
        assets.write_text(cat_path.read_text(encoding="utf-8"), encoding="utf-8")

    mins = [
        {
            "code": a["code"],
            "name": a["name"],
            "url": a["url"],
            "country": a["country"],
            "authority_type": a["authority_type"],
        }
        for a in AUTHORITIES
    ]
    _write(WEB / "saudi_ministries.json", mins)
    _write(ROOT / "data" / "saudi_ministries.json", mins)
    _write(WEB / "laws_catalog.json", [])

    for name in EMPTY_LIST_FILES:
        p = WEB / name
        _write(p, {} if name == "seen_items.json" else [])

    by_j = Counter(p.get("jurisdiction") or "Unknown" for p in kept)
    _write(
        WEB / "meta.json",
        {
            "generated_at": now,
            "site_scope": "Saudi ministries (SDAIA, TGA, MC, MEWA)",
            "counts": {
                "pdfs": len(kept),
                "jurisdictions": len(by_j),
                "authorities": len(AUTHORITIES),
            },
            "message": f"Saudi ministries · {len(kept)} PDFs · {len(AUTHORITIES)} authorities",
        },
    )

    # Eva: keep summaries for allowed ministries only
    eva_path = WEB / "eva_summaries.json"
    eva_n = 0
    if eva_path.exists():
        try:
            eva = json.loads(eva_path.read_text(encoding="utf-8"))
            if isinstance(eva, list):
                eva_kept = []
                for e in eva:
                    if not isinstance(e, dict) or not is_allowed_ministry_row(e):
                        continue
                    e = dict(e)
                    e["jurisdiction"] = normalize_jurisdiction(e)
                    eva_kept.append(e)
                _write(eva_path, eva_kept)
                eva_n = len(eva_kept)
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
            "site_scope": "Saudi ministries (SDAIA, TGA, MC, MEWA)",
            "llm_available": False,
        },
    )

    st = {
        "updated_at": now,
        "phase": "idle",
        "message": f"Saudi ministries · {len(kept)} PDFs · {eva_n} summaries",
        "totals": {
            "pdfs": len(kept),
            "errors": 0,
            "source_reports": 0,
            "jurisdictions": len(by_j),
        },
        "by_jurisdiction": [{"jurisdiction": j, "count": c} for j, c in by_j.most_common()],
        "by_source_kind": [{"source_kind": "ministry", "count": len(kept)}],
        "current_source": None,
        "recent_pdfs": [],
        "last_source_reports": [],
        "stats": {},
    }
    mdl_path = WEB / "ministry_document_list.json"
    if mdl_path.exists():
        try:
            mdl = json.loads(mdl_path.read_text(encoding="utf-8"))
            st["ministry_document_list"] = {
                "label": mdl.get("label"),
                "target_url": mdl.get("target_url"),
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
    _write(WEB / "crawl_status.json", st)
    print(
        f"Saudi ministries publish: {len(kept)} PDFs, {eva_n} Eva summaries, "
        f"authorities={len(AUTHORITIES)}"
    )


if __name__ == "__main__":
    main()

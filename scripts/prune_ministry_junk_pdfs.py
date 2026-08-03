#!/usr/bin/env python3
"""Remove non-regulatory ministry PDFs from the manifest + rebuild catalog.

Keeps bills/gazettes from other jurisdictions untouched.
Drops Saudi ministry junk (IoT, workshops, newsletters, citizen flyers, …).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from pdf_relevance import is_regulatory_pdf  # noqa: E402

MANIFEST = ROOT / "data" / "pdfs" / "manifest.json"


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not MANIFEST.exists():
        print("No manifest at", MANIFEST)
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    downloads = data.get("downloads") or []
    keep, drop = [], []
    for rec in downloads:
        jur = str(rec.get("jurisdiction") or "")
        kind = str(rec.get("source_kind") or "")
        is_ministry = kind == "ministry" or jur.startswith("Saudi Arabia")
        if not is_ministry:
            keep.append(rec)
            continue
        url = str(rec.get("url") or "")
        title = str(rec.get("title") or "")
        path = str(rec.get("path") or rec.get("local_path") or "")
        filename = Path(path).name if path else Path(urlparse_safe(url)).name
        if is_regulatory_pdf(url=url, title=title, filename=filename, min_score=15):
            keep.append(rec)
        else:
            drop.append(rec)

    print(f"manifest downloads: {len(downloads)}")
    print(f"keep: {len(keep)}  drop ministry junk: {len(drop)}")
    by = {}
    for r in drop:
        j = r.get("jurisdiction") or "?"
        by[j] = by.get(j, 0) + 1
    for j, n in sorted(by.items(), key=lambda x: -x[1]):
        print(f"  drop {n:4d}  {j}")
    for r in drop[:20]:
        fn = Path(str(r.get("path") or r.get("url") or "")).name
        print(f"    - {fn[:90]}")

    if dry:
        print("dry-run: no write")
        return 0

    data["downloads"] = keep
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", MANIFEST)

    # rebuild catalog for web
    from live_publish import publish

    publish(phase="idle", message=f"pruned {len(drop)} non-regulatory ministry PDFs", force_git=False)
    print("catalog rebuilt")
    return 0


def urlparse_safe(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path or url


if __name__ == "__main__":
    raise SystemExit(main())

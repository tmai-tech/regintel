#!/usr/bin/env python3
"""Merge per-ministry crawl artifacts into main manifest + rebuild catalog."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "pdfs" / "manifest.json"
ART_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "_ministry_out")


def main() -> int:
    if MANIFEST.exists():
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    else:
        data = {"downloads": [], "errors": [], "source_reports": [], "stats": {}}
    downloads = list(data.get("downloads") or [])
    by_url = {d.get("url"): d for d in downloads if d.get("url")}
    added = 0
    by_code: dict[str, int] = {}

    if not ART_DIR.exists():
        print("No artifacts dir", ART_DIR)
        return 0

    for path in sorted(ART_DIR.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print("skip", path, e)
            continue
        items = payload if isinstance(payload, list) else payload.get("downloads") or []
        for rec in items:
            if rec.get("dry_run"):
                continue
            url = rec.get("url")
            if not url or url in by_url:
                continue
            by_url[url] = rec
            downloads.append(rec)
            added += 1
            j = str(rec.get("jurisdiction") or "?")
            by_code[j] = by_code.get(j, 0) + 1

    data["downloads"] = downloads
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"merged +{added} downloads; total={len(downloads)}")
    for j, n in sorted(by_code.items(), key=lambda x: -x[1]):
        print(f"  +{n}  {j}")

    sys.path.insert(0, str(ROOT / "collector"))
    from live_publish import publish

    publish(
        phase="idle",
        message=f"merged {added} ministry PDFs from parallel crawl",
        force_git=False,
    )
    print("catalog rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

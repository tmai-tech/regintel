#!/usr/bin/env python3
"""Re-label PDF catalog rows so host matches Saudi ministry (fixes 0 on Ministries tab).

Example bug: sdaia.gov.sa PDFs stored as 'Saudi Arabia - NCA' / MoC / MOMAH
because BFS collected cross-host PDFs. Ministries tab host-match should still
find them, but label match fails and merge skips re-add by URL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "pdfs" / "manifest.json"
MINISTRIES = ROOT / "data" / "saudi_ministries.json"


def base_host(url_or_host: str) -> str:
    raw = (url_or_host or "").strip().lower()
    if "://" in raw:
        raw = urlparse(raw).netloc
    return raw.removeprefix("www.")


def main() -> int:
    dry = "--dry-run" in sys.argv
    ministries = json.loads(MINISTRIES.read_text(encoding="utf-8"))
    # longest host first so rulebook.sama.gov.sa beats sama.gov.sa if both listed
    host_to_jur: list[tuple[str, str]] = []
    for m in ministries:
        code = m.get("code") or ""
        host = base_host(m.get("url") or "")
        if not host or not code:
            continue
        jur = f"Saudi Arabia - {code}"
        host_to_jur.append((host, jur))
        # companion hosts
        if host == "sama.gov.sa":
            host_to_jur.append(("rulebook.sama.gov.sa", jur))
        if host == "moj.gov.sa":
            host_to_jur.append(("laws.moj.gov.sa", jur))
        if host == "sdaia.gov.sa":
            host_to_jur.append(("dgp.sdaia.gov.sa", jur))
            host_to_jur.append(("ndmo.sdaia.gov.sa", jur))
        if host == "cma.org.sa":
            host_to_jur.append(("cma.gov.sa", jur))
    host_to_jur.sort(key=lambda x: -len(x[0]))

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    downloads = data.get("downloads") or []
    changed = 0
    samples = []
    for rec in downloads:
        url = rec.get("url") or ""
        h = base_host(url)
        if not h:
            continue
        new_jur = None
        for mh, jur in host_to_jur:
            if h == mh or h.endswith("." + mh):
                new_jur = jur
                break
        if not new_jur:
            continue
        old = rec.get("jurisdiction") or ""
        if old != new_jur:
            rec["jurisdiction"] = new_jur
            rec["source_kind"] = rec.get("source_kind") or "ministry"
            changed += 1
            if len(samples) < 15:
                samples.append(f"{old!r} → {new_jur}  {Path(url).name[:60]}")

    print(f"relabeled {changed} downloads")
    for s in samples:
        print(" ", s)

    if dry:
        print("dry-run: no write")
        return 0

    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(ROOT / "collector"))
    from live_publish import publish

    publish(phase="idle", message=f"relabeled {changed} ministry PDFs by host", force_git=False)
    print("catalog rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

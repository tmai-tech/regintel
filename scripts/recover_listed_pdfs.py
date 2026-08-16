#!/usr/bin/env python3
"""Download ministry-list URLs that never landed in the public catalog."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT / "scripts"))

from live_publish import publish  # type: ignore
from ministry_pipeline import MinistryPipeline  # type: ignore
from saudi_ministry_allowlist import AUTHORITIES  # type: ignore

TARGETS = (
    ("MOMAH", "https://momah.gov.sa", "Saudi Arabia - MOMAH", "data/pdfs/ministry_lists/momahgovsa.json", "data/momah_found_docs.txt"),
    ("ZATCA", "https://zatca.gov.sa", "Saudi Arabia - ZATCA", "data/pdfs/ministry_lists/zatcagovsa.json", "data/zatca_found_docs.txt"),
    ("SASO", "https://www.saso.gov.sa", "Saudi Arabia - SASO", "data/pdfs/ministry_lists/sasogovsa.json", ""),
    ("GOSI", "https://www.gosi.gov.sa", "Saudi Arabia - GOSI", "data/pdfs/ministry_lists/gosigovsa.json", ""),
)


def catalog_urls() -> set[str]:
    p = ROOT / "web" / "data" / "pdfs_catalog.json"
    if not p.exists():
        return set()
    rows = json.loads(p.read_text(encoding="utf-8"))
    return {(r.get("open_url") or r.get("url") or "").strip() for r in rows if r.get("url") or r.get("open_url")}


def urls_from_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for d in data.get("documents") or []:
        u = (d.get("url") or "").strip()
        if u.startswith("http"):
            out.append(u)
    return out


def urls_from_txt(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("http")]


def recover_one(code: str, url: str, label: str, list_rel: str, seed_rel: str, have: set[str]) -> dict:
    listed: list[str] = []
    listed.extend(urls_from_list(ROOT / list_rel))
    if seed_rel:
        listed.extend(urls_from_txt(ROOT / seed_rel))
    missing = []
    seen = set()
    for u in listed:
        if u in have or u in seen:
            continue
        seen.add(u)
        missing.append(u)
    print(f"\n=== {code} listed={len(seen)+len([u for u in listed if u in have])} missing={len(missing)} ===", flush=True)
    if not missing:
        return {"code": code, "missing": 0, "ok": 0, "fail": 0}

    tmp = ROOT / "data" / f"_recover_{code.lower()}.txt"
    tmp.write_text("\n".join(missing) + "\n", encoding="utf-8")
    pipe = MinistryPipeline(
        url=url,
        label=label,
        max_pages=1,
        delay=0.15,
        download=True,
        insecure=True,
        seed_list=str(tmp),
    )
    pipe.publish_status = lambda *a, **k: None  # no mid-batch catalog/git/firestore
    pipe.load_seed_list(str(tmp))
    for rec in pipe.docs.values():
        dest = pipe.out_dir / (rec.get("filename") or "x.pdf")
        if dest.is_file() and dest.stat().st_size > 128:
            rec["status"] = "downloaded"
            rec["local_path"] = str(dest.relative_to(ROOT))
            rec["bytes"] = dest.stat().st_size
    stats = pipe.download_all(complete=True)
    pipe.merge_into_manifest()
    ok = int(stats.get("downloaded") or 0) + int(stats.get("scanned_pdf") or 0)
    fail = int(stats.get("download_failed") or 0)
    print(f"[{code}] drain ok={ok} fail={fail}", flush=True)
    return {"code": code, "missing": len(missing), "ok": ok, "fail": fail}


def main() -> None:
    have = catalog_urls()
    results = []
    for code, url, label, lst, seed in TARGETS:
        results.append(recover_one(code, url, label, lst, seed, have))
        # refresh known URLs so later sites skip anything just added
        have = catalog_urls()
        # also skip manifest urls not yet in catalog
        man = ROOT / "data" / "pdfs" / "manifest.json"
        if man.exists():
            m = json.loads(man.read_text(encoding="utf-8"))
            for d in m.get("downloads") or []:
                if d.get("url"):
                    have.add(d["url"])

    publish(
        phase="idle",
        message="recovered listed PDFs after failed live-publish rebases",
        git_push=False,
        force_git=False,
    )
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()

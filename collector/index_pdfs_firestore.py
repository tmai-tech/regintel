#!/usr/bin/env python3
"""Index local gazette PDF downloads into Firestore + web/data for the app."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "pdfs" / "manifest.json"
WEB_CATALOG = ROOT / "web" / "data" / "pdfs_catalog.json"
ASSETS_CATALOG = ROOT / "android" / "app" / "src" / "main" / "assets" / "pdfs_catalog.json"


def init(sa_path: str | None):
    if firebase_admin._apps:
        return firestore.client()
    path = sa_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        cand = ROOT / ".secrets" / "roomcraft-e1312-firebase-adminsdk-fbsvc.json"
        if cand.exists():
            path = str(cand)
    if not path or not Path(path).exists():
        raise SystemExit("Missing service account")
    firebase_admin.initialize_app(credentials.Certificate(path))
    return firestore.client()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--service-account")
    ap.add_argument("--skip-firestore", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    downloads = manifest.get("downloads") or []
    catalog = []
    for i, rec in enumerate(downloads):
        local = ROOT / (rec.get("path") or "")
        size = rec.get("bytes") or (local.stat().st_size if local.is_file() else 0)
        filename = local.name if rec.get("path") else (rec.get("title") or f"doc_{i}.pdf")
        # Prefer original PDF URL for opening in app (no Storage billing)
        open_url = rec.get("download_url") or rec.get("url")
        item = {
            "id": rec.get("sha256") or f"pdf_{i}",
            "title": rec.get("title") or filename,
            "filename": filename,
            "jurisdiction": rec.get("jurisdiction"),
            "source_kind": rec.get("source_kind"),
            "source_page": rec.get("source_page"),
            "url": rec.get("url"),  # original source PDF URL
            "open_url": open_url,
            "download_url": rec.get("download_url"),
            "bytes": size,
            "sha256": rec.get("sha256"),
            "downloaded_at": rec.get("downloaded_at"),
            "local_path": rec.get("path"),
        }
        catalog.append(item)

    # Sort newest first when possible
    catalog.sort(key=lambda x: x.get("downloaded_at") or "", reverse=True)

    for path in (WEB_CATALOG, ASSETS_CATALOG):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {path} ({len(catalog)} items)")

    if args.skip_firestore:
        return

    db = init(args.service_account)
    batch = db.batch()
    pending = 0
    written = 0
    for item in catalog:
        ref = db.collection("regintel_pdfs").document(str(item["id"])[:80])
        batch.set(ref, item, merge=True)
        pending += 1
        written += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0
            print(f"  firestore {written}…")
    if pending:
        batch.commit()

    db.collection("regintel_meta").document("pdfs").set(
        {
            "total_indexed": len(catalog),
            "last_index_at": datetime.now(timezone.utc).isoformat(),
            "note": "open_url points at original source PDF (Firebase Storage billing not enabled)",
        },
        merge=True,
    )
    db.collection("regintel_meta").document("catalog").set(
        {"pdf_count": len(catalog)},
        merge=True,
    )
    print(f"Indexed {written} PDFs in Firestore regintel_pdfs")


if __name__ == "__main__":
    main()

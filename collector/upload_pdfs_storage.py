#!/usr/bin/env python3
"""Upload downloaded gazette/bill PDFs to Firebase Storage + index in Firestore."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import firebase_admin
from firebase_admin import credentials, firestore, storage

ROOT = Path(__file__).resolve().parents[1]
PDF_ROOT = ROOT / "data" / "pdfs"
MANIFEST = PDF_ROOT / "manifest.json"
DEFAULT_BUCKET = "roomcraft-e1312.firebasestorage.app"


def init(sa_path: str | None, bucket: str):
    if firebase_admin._apps:
        return firestore.client(), storage.bucket(bucket)
    path = sa_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        cand = ROOT / ".secrets" / "roomcraft-e1312-firebase-adminsdk-fbsvc.json"
        if cand.exists():
            path = str(cand)
    if not path or not Path(path).exists():
        raise SystemExit("Missing service account — set GOOGLE_APPLICATION_CREDENTIALS")
    cred = credentials.Certificate(path)
    firebase_admin.initialize_app(cred, {"storageBucket": bucket})
    return firestore.client(), storage.bucket(bucket)


def download_url(bucket_name: str, path: str, token: str) -> str:
    encoded = quote(path, safe="")
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/"
        f"{encoded}?alt=media&token={token}"
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--service-account")
    p.add_argument("--bucket", default=DEFAULT_BUCKET)
    p.add_argument("--limit", type=int, default=0, help="Max files to upload (0=all)")
    p.add_argument("--prefix", default="regintel/pdfs")
    args = p.parse_args()

    db, bucket = init(args.service_account, args.bucket)
    if not MANIFEST.exists():
        raise SystemExit(f"No manifest at {MANIFEST}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    downloads = manifest.get("downloads") or []

    uploaded = skipped = errors = 0
    for i, rec in enumerate(downloads):
        if args.limit and uploaded >= args.limit:
            break
        rel = rec.get("path")
        if not rel:
            skipped += 1
            continue
        local = ROOT / rel
        if not local.is_file():
            skipped += 1
            continue

        jur = (rec.get("jurisdiction") or "unknown").replace(" ", "_")
        kind = (rec.get("source_kind") or "other").replace(" ", "_")
        safe_name = local.name.replace(" ", "_")
        dest_path = f"{args.prefix}/{jur}/{kind}/{safe_name}"
        blob = bucket.blob(dest_path)

        try:
            token = None
            if rec.get("storage_path") == dest_path and rec.get("download_url") and blob.exists():
                skipped += 1
                token = rec.get("download_token")
            else:
                token = str(uuid.uuid4())
                ctype = mimetypes.guess_type(local.name)[0] or "application/pdf"
                blob.metadata = {"firebaseStorageDownloadTokens": token}
                blob.upload_from_filename(str(local), content_type=ctype)
                # ensure token metadata applied
                blob.metadata = {"firebaseStorageDownloadTokens": token}
                blob.patch()
                rec["storage_path"] = dest_path
                rec["storage_uploaded"] = True
                rec["download_token"] = token
                rec["download_url"] = download_url(args.bucket, dest_path, token)
                rec["gs_uri"] = f"gs://{args.bucket}/{dest_path}"
                rec["uploaded_at"] = datetime.now(timezone.utc).isoformat()
                uploaded += 1
                print(f"[up {uploaded}] {dest_path} ({local.stat().st_size} bytes)")

            if not rec.get("download_url") and token:
                rec["download_url"] = download_url(args.bucket, dest_path, token)

            doc_id = rec.get("sha256") or f"pdf_{i}_{uuid.uuid4().hex[:8]}"
            db.collection("regintel_pdfs").document(str(doc_id)[:80]).set(
                {
                    "title": rec.get("title") or safe_name,
                    "filename": safe_name,
                    "url": rec.get("url"),
                    "jurisdiction": rec.get("jurisdiction"),
                    "source_kind": rec.get("source_kind"),
                    "source_page": rec.get("source_page"),
                    "local_path": rec.get("path"),
                    "storage_path": rec.get("storage_path"),
                    "download_url": rec.get("download_url"),
                    "gs_uri": rec.get("gs_uri"),
                    "bytes": rec.get("bytes") or local.stat().st_size,
                    "sha256": rec.get("sha256"),
                    "downloaded_at": rec.get("downloaded_at"),
                    "uploaded_at": rec.get("uploaded_at"),
                },
                merge=True,
            )
        except Exception as e:
            errors += 1
            print(f"[err] {local}: {e}")

        if (uploaded + skipped) % 20 == 0:
            MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    indexed = sum(1 for d in downloads if d.get("download_url"))
    db.collection("regintel_meta").document("pdfs").set(
        {
            "total_indexed": indexed,
            "total_local": len(downloads),
            "last_upload_at": datetime.now(timezone.utc).isoformat(),
            "bucket": args.bucket,
            "prefix": args.prefix,
        },
        merge=True,
    )
    # also bump catalog meta
    db.collection("regintel_meta").document("catalog").set(
        {"pdf_count": indexed},
        merge=True,
    )
    print(json.dumps({"uploaded": uploaded, "skipped": skipped, "errors": errors, "indexed": indexed}, indent=2))


if __name__ == "__main__":
    main()

"""Best-effort Firestore writes for live crawl status (regintel_crawls / sites).

Admin SDK only. Missing credentials or firebase-admin → no-op so crawlers
still work with git JSON.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COL_CRAWLS = "regintel_crawls"
COL_SITES = "regintel_sites"
COL_META = "regintel_meta"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db():
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        print("[firestore] firebase-admin not installed", flush=True)
        return None

    if firebase_admin._apps:
        from firebase_admin import firestore as fs

        return fs.client()

    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not path or not Path(str(path)).exists():
        cand = ROOT / ".secrets" / "roomcraft-e1312-firebase-adminsdk-fbsvc.json"
        if cand.exists():
            path = str(cand)
    try:
        if path and Path(path).exists():
            cred = credentials.Certificate(path)
        elif raw and raw.strip().startswith("{"):
            cred = credentials.Certificate(json.loads(raw))
        else:
            print("[firestore] no credentials; skip live write", flush=True)
            return None
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"[firestore] init failed: {e}", flush=True)
        return None


def upsert_crawl_job(job: dict | None) -> bool:
    if not job or not job.get("code"):
        return False
    db = get_db()
    if db is None:
        return False
    code = str(job["code"]).upper()
    payload = {
        "code": code,
        "url": job.get("url") or "",
        "label": job.get("label") or f"Saudi Arabia - {code}",
        "phase": job.get("phase") or "running",
        "message": job.get("message") or "",
        "pages": int(job.get("pages") or 0),
        "listed": int(job.get("listed") or 0),
        "downloaded": int(job.get("downloaded") or 0),
        "to_download": int(job.get("to_download") or 0),
        "run_id": str(job.get("run_id") or os.environ.get("GITHUB_RUN_ID") or ""),
        "updated_at": job.get("updated_at") or _now(),
    }
    db.collection(COL_CRAWLS).document(code).set(payload, merge=True)
    print(f"[firestore] upsert {COL_CRAWLS}/{code} phase={payload['phase']}", flush=True)
    return True


def upsert_sites(sites: list[dict]) -> int:
    db = get_db()
    if db is None:
        return 0
    n = 0
    batch = db.batch()
    pending = 0
    for s in sites:
        code = str(s.get("code") or "").upper()
        if not code:
            continue
        batch.set(
            db.collection(COL_SITES).document(code),
            {
                "code": code,
                "name": s.get("name") or code,
                "url": s.get("url") or "",
                "label": s.get("label") or f"Saudi Arabia - {code}",
                "pdf_count": int(s.get("pdf_count") or s.get("count") or 0),
                "updated_at": _now(),
            },
            merge=True,
        )
        pending += 1
        n += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()
    db.collection(COL_META).document("sites").set(
        {"count": n, "updated_at": _now()}, merge=True
    )
    print(f"[firestore] upsert {n} {COL_SITES}", flush=True)
    return n

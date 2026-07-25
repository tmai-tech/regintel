#!/usr/bin/env python3
"""Upload RegIntel JSON catalog + updates to Firestore (Admin SDK)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def init_app(sa_path: str | None):
    if firebase_admin._apps:
        return firestore.client()
    path = sa_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        # local default
        cand = ROOT / ".secrets" / "roomcraft-e1312-firebase-adminsdk-fbsvc.json"
        if cand.exists():
            path = str(cand)
    if not path or not Path(path).exists():
        raise SystemExit(
            "Set GOOGLE_APPLICATION_CREDENTIALS or pass --service-account"
        )
    cred = credentials.Certificate(path)
    firebase_admin.initialize_app(cred)
    return firestore.client()


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def doc_id(prefix: str, *parts: str) -> str:
    raw = "|".join(p or "" for p in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode()).hexdigest()[:20]}"


def batch_set(db, collection: str, docs: list[tuple[str, dict]], wipe: bool):
    col = db.collection(collection)
    if wipe:
        # delete existing in pages
        while True:
            snaps = list(col.limit(400).stream())
            if not snaps:
                break
            b = db.batch()
            for s in snaps:
                b.delete(s.reference)
            b.commit()
            print(f"  wiped {len(snaps)} from {collection}")

    written = 0
    batch = db.batch()
    pending = 0
    for did, data in docs:
        batch.set(col.document(did), data, merge=True)
        pending += 1
        written += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0
            print(f"  {collection}: {written}…")
    if pending:
        batch.commit()
    print(f"  {collection}: wrote {written}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--service-account", default=None)
    p.add_argument("--wipe", action="store_true", help="Delete existing collection docs first")
    p.add_argument(
        "--only",
        choices=["all", "tracking", "primary", "updates", "gazette", "secondary", "meta"],
        default="all",
    )
    args = p.parse_args()
    db = init_app(args.service_account)

    only = args.only
    if only in ("all", "tracking"):
        tracking = load("tracking.json")
        docs = []
        for i, r in enumerate(tracking):
            did = doc_id("tr", r.get("link") or "", r.get("remarks") or "", str(i))
            docs.append((did, r))
        print("Uploading tracking…")
        batch_set(db, "regintel_tracking", docs, args.wipe)

    if only in ("all", "primary"):
        primary = load("primary_sources.json")
        docs = []
        for i, r in enumerate(primary):
            did = doc_id("ps", r.get("url") or "", r.get("authority") or "", str(i))
            docs.append((did, r))
        print("Uploading primary sources…")
        batch_set(db, "regintel_primary_sources", docs, args.wipe)

    if only in ("all", "updates"):
        updates = load("updates.json")
        docs = []
        for r in updates:
            did = r.get("id") or doc_id("up", r.get("link") or "", r.get("title") or "")
            docs.append((did, r))
        print("Uploading updates…")
        batch_set(db, "regintel_updates", docs, args.wipe)

    if only in ("all", "gazette"):
        gazette = load("gazette.json")
        docs = []
        for i, r in enumerate(gazette):
            did = doc_id("gz", r.get("jurisdiction") or "", str(i))
            docs.append((did, r))
        print("Uploading gazette…")
        batch_set(db, "regintel_gazette", docs, args.wipe)

    if only in ("all", "secondary"):
        secondary = load("secondary_sources.json")
        docs = []
        for i, r in enumerate(secondary):
            did = doc_id("sc", r.get("name") or "", r.get("url") or "", str(i))
            docs.append((did, r))
        print("Uploading secondary…")
        batch_set(db, "regintel_secondary", docs, args.wipe)

    if only in ("all", "meta"):
        meta = load("meta.json")
        counts = meta.get("counts") or {}
        payload = {
            "generated_at": meta.get("generated_at"),
            "last_collector_run": meta.get("last_collector_run"),
            "primary_sources": counts.get("primary_sources", 0),
            "tracking_records": counts.get("tracking_records", 0),
            "gazette_sources": counts.get("gazette_sources", 0),
            "secondary_sources": counts.get("secondary_sources", 0),
            "updates": counts.get("updates", 0),
            "last_collector_stats": meta.get("last_collector_stats"),
        }
        db.collection("regintel_meta").document("catalog").set(payload, merge=True)
        print("Uploaded meta/catalog")

    print("Done.")


if __name__ == "__main__":
    main()

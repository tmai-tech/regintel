#!/usr/bin/env python3
"""Publish PDF catalog + crawl status for the live site as soon as PDFs are found.

Writes:
  web/data/pdfs_catalog.json
  web/data/crawl_status.json
  data/pdfs/crawl_status.json
  (optional) android assets catalog

Optional git commit+push when GITHUB_ACTIONS=true or REGINTEL_LIVE_GIT_PUSH=1.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "pdfs" / "manifest.json"
WEB_DATA = ROOT / "web" / "data"
WEB_CATALOG = WEB_DATA / "pdfs_catalog.json"
WEB_STATUS = WEB_DATA / "crawl_status.json"
LOCAL_STATUS = ROOT / "data" / "pdfs" / "crawl_status.json"
ASSETS_CATALOG = ROOT / "android" / "app" / "src" / "main" / "assets" / "pdfs_catalog.json"

# throttle git pushes
_last_git_push = 0.0
_last_catalog_count = -1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"downloads": [], "errors": [], "source_reports": [], "stats": {}}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"downloads": [], "errors": [], "source_reports": [], "stats": {}}


def build_catalog_from_manifest(manifest: dict | None = None) -> list[dict]:
    """Reuse enrich_record from index_pdfs_firestore (no Firestore)."""
    import sys

    sys.path.insert(0, str(ROOT / "collector"))
    try:
        from index_pdfs_firestore import enrich_record
    except ImportError:
        from collector.index_pdfs_firestore import enrich_record  # type: ignore

    manifest = manifest or load_manifest()
    downloads = manifest.get("downloads") or []
    catalog = []
    for i, rec in enumerate(downloads):
        if rec.get("dry_run"):
            continue
        try:
            catalog.append(enrich_record(rec, i))
        except Exception:
            # minimal fallback so live site still lists the link
            catalog.append(
                {
                    "id": rec.get("sha256") or f"pdf_{i}",
                    "title": rec.get("title") or rec.get("url") or f"PDF {i}",
                    "filename": Path(rec.get("path") or "doc.pdf").name,
                    "jurisdiction": rec.get("jurisdiction"),
                    "source_kind": rec.get("source_kind"),
                    "url": rec.get("url"),
                    "open_url": rec.get("url"),
                    "source_page": rec.get("source_page"),
                    "bytes": rec.get("bytes") or 0,
                    "downloaded_at": rec.get("downloaded_at"),
                    "status": "downloaded",
                }
            )
    catalog.sort(
        key=lambda r: (r.get("downloaded_at") or "", r.get("jurisdiction") or "", r.get("title") or ""),
        reverse=True,
    )
    return catalog


def build_status(
    *,
    phase: str = "running",
    message: str = "",
    current_source: dict | None = None,
    run_id: str | None = None,
) -> dict:
    manifest = load_manifest()
    downloads = [d for d in (manifest.get("downloads") or []) if not d.get("dry_run")]
    errors = manifest.get("errors") or []
    reports = manifest.get("source_reports") or []
    by_j = Counter(d.get("jurisdiction") or "Unknown" for d in downloads)
    by_kind = Counter(d.get("source_kind") or "unknown" for d in downloads)
    recent = sorted(
        downloads,
        key=lambda d: d.get("downloaded_at") or "",
        reverse=True,
    )[:15]
    recent_slim = [
        {
            "title": (r.get("title") or r.get("url") or "")[:120],
            "jurisdiction": r.get("jurisdiction"),
            "url": r.get("url"),
            "downloaded_at": r.get("downloaded_at"),
            "source_kind": r.get("source_kind"),
        }
        for r in recent
    ]
    return {
        "updated_at": _now(),
        "phase": phase,
        "message": message,
        "run_id": run_id or os.environ.get("GITHUB_RUN_ID") or os.environ.get("REGINTEL_RUN_ID"),
        "github_run_url": (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY")
            else None
        ),
        "totals": {
            "pdfs": len(downloads),
            "errors": len(errors),
            "source_reports": len(reports),
            "jurisdictions": len(by_j),
        },
        "by_jurisdiction": [
            {"jurisdiction": j, "count": c} for j, c in by_j.most_common(40)
        ],
        "by_source_kind": [
            {"source_kind": k, "count": c} for k, c in by_kind.most_common()
        ],
        "current_source": current_source,
        "recent_pdfs": recent_slim,
        "last_source_reports": reports[-12:],
        "stats": manifest.get("stats") or {},
        "manifest_generated_at": manifest.get("generated_at"),
    }


def publish(
    *,
    phase: str = "running",
    message: str = "",
    current_source: dict | None = None,
    git_push: bool | None = None,
    force_git: bool = False,
    min_git_interval_sec: float = 180.0,
) -> dict:
    """Rebuild catalog + status JSON. Optionally commit/push for live site."""
    global _last_git_push, _last_catalog_count

    manifest = load_manifest()
    catalog = build_catalog_from_manifest(manifest)
    status = build_status(
        phase=phase, message=message, current_source=current_source
    )
    status["totals"]["pdfs"] = len(catalog)

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "pdfs").mkdir(parents=True, exist_ok=True)

    WEB_CATALOG.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    WEB_STATUS.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LOCAL_STATUS.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if ASSETS_CATALOG.parent.is_dir():
        ASSETS_CATALOG.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    n = len(catalog)
    do_git = git_push
    if do_git is None:
        do_git = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get(
            "REGINTEL_LIVE_GIT_PUSH"
        ) == "1"

    if do_git and (force_git or n != _last_catalog_count):
        now = time.time()
        if force_git or (now - _last_git_push) >= min_git_interval_sec:
            if _git_push_live(n, status.get("phase") or phase):
                _last_git_push = now
                _last_catalog_count = n

    return status


def _git_remote_with_token() -> str | None:
    """Build authenticated remote URL for Actions (GITHUB_TOKEN)."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")  # owner/name
    if token and repo:
        return f"https://x-access-token:{token}@github.com/{repo}.git"
    return None


def _run_git(args: list[str], *, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
    )


def _git_push_live(pdf_count: int, phase: str) -> bool:
    """Commit catalog/status/manifest so deploy + resume work.

    On GitHub Actions, use GITHUB_TOKEN in the remote URL (plain `git push origin`
    often fails with exit 1 under concurrent jobs / default credential setup).
    """
    try:
        env = os.environ.copy()
        _run_git(["config", "user.name", "github-actions[bot]"])
        _run_git(
            [
                "config",
                "user.email",
                "41898282+github-actions[bot]@users.noreply.github.com",
            ]
        )

        remote = _git_remote_with_token()
        # Always fetch latest main before commit to reduce non-fast-forward
        if remote:
            fr = _run_git(["fetch", remote, "main:refs/remotes/origin/main"], env=env)
            if fr.returncode != 0:
                print(f"[live-publish] fetch warn: {fr.stderr.strip()[:300]}", flush=True)
            _run_git(["rebase", "origin/main"], env=env)
        else:
            _run_git(["pull", "--rebase", "origin", "main"], env=env)

        paths = [
            "data/pdfs/manifest.json",
            "data/pdfs/crawl_status.json",
            "web/data/pdfs_catalog.json",
            "web/data/crawl_status.json",
            "web/data/pdfs_coverage.json",
            "android/app/src/main/assets/pdfs_catalog.json",
        ]
        for p in paths:
            if (ROOT / p).exists():
                _run_git(["add", "-f", p])

        st = _run_git(["diff", "--staged", "--quiet"])
        if st.returncode == 0:
            return False  # nothing staged

        msg = f"chore: live PDF catalog ({pdf_count} pdfs, {phase}) {_now()}"
        cr = _run_git(["commit", "-m", msg], env=env)
        if cr.returncode != 0:
            print(
                f"[live-publish] commit failed: {(cr.stderr or cr.stdout)[:400]}",
                flush=True,
            )
            return False

        # Retry push a few times (concurrent crawl/schedule races)
        last_err = ""
        for attempt in range(1, 4):
            if remote:
                pr = _run_git(["push", remote, "HEAD:main"], env=env)
            else:
                pr = _run_git(["push", "origin", "HEAD:main"], env=env)
            if pr.returncode == 0:
                print(f"[live-publish] pushed catalog ({pdf_count} PDFs)", flush=True)
                return True
            last_err = (pr.stderr or pr.stdout or "")[:500]
            print(f"[live-publish] push attempt {attempt} failed: {last_err}", flush=True)
            # rebase on latest and retry
            if remote:
                _run_git(["fetch", remote, "main:refs/remotes/origin/main"], env=env)
            _run_git(["rebase", "origin/main"], env=env)
            time.sleep(2 * attempt)

        print(f"[live-publish] git push failed after retries: {last_err}", flush=True)
        return False
    except Exception as e:
        print(f"[live-publish] git push skipped/failed: {e}", flush=True)
        return False


if __name__ == "__main__":
    s = publish(phase="manual", message="manual live_publish", force_git=False)
    print(json.dumps(s["totals"], indent=2))

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
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "pdfs" / "manifest.json"
WEB_DATA = ROOT / "web" / "data"
WEB_CATALOG = WEB_DATA / "pdfs_catalog.json"
WEB_STATUS = WEB_DATA / "crawl_status.json"
WEB_CRAWLS_DIR = WEB_DATA / "crawls"
WEB_ACTIVE = WEB_DATA / "active_crawls.json"
LOCAL_STATUS = ROOT / "data" / "pdfs" / "crawl_status.json"
ASSETS_CATALOG = ROOT / "android" / "app" / "src" / "main" / "assets" / "pdfs_catalog.json"

# UI treats these as finished so devices do not keep an old "in progress" card.
_DONE_PHASES = frozenset({"idle", "complete", "stopped", "listed", "manual"})

# throttle git pushes
_last_git_push = 0.0
_last_catalog_count = -1
_last_listed_count = -1
_last_pages_seen = -1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ministry_code_from(url: str = "", label: str = "") -> str:
    """Stable site code so every device keys the same job (MOMAH, MC, …)."""
    blob = f"{label} {url}".lower()
    pairs = (
        ("sdaia", "SDAIA"),
        ("dgp.sdaia", "SDAIA"),
        ("mewa", "MEWA"),
        ("tga.gov", "TGA"),
        ("mc.gov", "MC"),
        ("momah", "MOMAH"),
        ("mof.gov", "MOF"),
        ("nca.gov", "NCA"),
        ("socpa", "SOCPA"),
        ("moi.gov", "MOI"),
        ("nazaha", "NAZAHA"),
        ("sama.gov", "SAMA"),
        ("rulebook.sama", "SAMA"),
        ("moj.gov", "MOJ"),
        ("gac.gov", "GAC"),
        ("cst.gov", "CST"),
        ("cma.org", "CMA"),
        ("saudiexchange", "TADAWUL"),
        ("tadawul", "TADAWUL"),
        ("gosi.gov", "GOSI"),
        ("saso.gov", "SASO"),
        ("saip.gov", "SAIP"),
        ("zatca", "ZATCA"),
        ("ia.gov", "IA"),
    )
    for needle, code in pairs:
        if needle in blob:
            return code
    lab = (label or "").strip()
    if " - " in lab:
        tail = lab.rsplit(" - ", 1)[-1].strip().upper()
        if tail == "NAZAHA":
            return "NAZAHA"
        if tail == "TADAWUL":
            return "TADAWUL"
        if tail and tail.replace(" ", "").isalnum() and len(tail) <= 12:
            return tail
    return ""


def _ui_phase(phase: str) -> str:
    p = str(phase or "").lower()
    if p in _DONE_PHASES:
        return "stopped" if p in {"idle", "complete", "stopped", "manual"} else p
    return p or "running"


def job_snapshot(
    status: dict,
    current_source: dict | None = None,
    ministry_progress: dict | None = None,
) -> dict | None:
    cur = current_source or status.get("current_source") or {}
    prog = ministry_progress or status.get("ministry_document_list") or {}
    counts = prog.get("counts") or {}
    url = cur.get("url") or prog.get("target_url") or ""
    label = cur.get("jurisdiction") or prog.get("label") or ""
    code = ministry_code_from(url, label)
    if not code:
        return None
    listed = cur.get("listed")
    if listed is None:
        listed = counts.get("listed_total", 0)
    downloaded = int(cur.get("downloaded") or counts.get("downloaded") or 0) + int(
        cur.get("scanned_pdf") or counts.get("scanned_pdf") or 0
    )
    to_download = cur.get("to_download")
    if to_download is None:
        to_download = counts.get("to_download")
    pages = cur.get("pages_visited")
    if pages is None:
        pages = prog.get("pages_visited") or 0
    phase = _ui_phase(status.get("phase") or "")
    return {
        "code": code,
        "url": url,
        "label": label,
        "phase": phase,
        "message": status.get("message") or "",
        "pages": pages or 0,
        "listed": listed or 0,
        "downloaded": downloaded,
        "to_download": to_download if to_download is not None else 0,
        "updated_at": status.get("updated_at") or _now(),
        "run_id": status.get("run_id"),
    }


def write_active_crawls(job: dict | None = None) -> dict:
    """Per-site files + merged index. Parallel jobs only overwrite their own code."""
    WEB_CRAWLS_DIR.mkdir(parents=True, exist_ok=True)
    if job and job.get("code"):
        path = WEB_CRAWLS_DIR / f"{job['code']}.json"
        path.write_text(
            json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    jobs: list[dict] = []
    for path in sorted(WEB_CRAWLS_DIR.glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(row, dict) or not row.get("code"):
            continue
        jobs.append(row)

    live = {"discovering", "downloading", "starting", "running", "queued"}
    jobs.sort(
        key=lambda j: (
            0 if str(j.get("phase") or "") in live else 1,
            str(j.get("code") or ""),
        )
    )
    payload = {"updated_at": _now(), "jobs": jobs}
    WEB_ACTIVE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


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


def _filter_public_catalog(catalog: list[dict]) -> list[dict]:
    """Keep only allowlisted Saudi ministries (SDAIA/TGA/MC/MEWA) on the public site."""
    # REGINTEL_SDAIA_ONLY=1 is legacy; prefer multi-ministry allowlist unless full catalog requested
    if os.environ.get("REGINTEL_FULL_CATALOG", "0") == "1":
        return catalog
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from saudi_ministry_allowlist import (  # type: ignore
            is_allowed_ministry_row,
            normalize_jurisdiction,
        )
    except Exception:
        # fallback: SDAIA only
        out = []
        for r in catalog:
            blob = (
                str(r.get("jurisdiction") or "")
                + str(r.get("host") or "")
                + str(r.get("url") or "")
            ).lower()
            if "sdaia" in blob:
                r = dict(r)
                r["jurisdiction"] = "Saudi Arabia - SDAIA"
                r["source_kind"] = r.get("source_kind") or "ministry"
                out.append(r)
        return out

    out = []
    for r in catalog:
        if not is_allowed_ministry_row(r):
            continue
        r = dict(r)
        r["jurisdiction"] = normalize_jurisdiction(r)
        r["source_kind"] = r.get("source_kind") or "ministry"
        out.append(r)
    return out


def publish(
    *,
    phase: str = "running",
    message: str = "",
    current_source: dict | None = None,
    ministry_progress: dict | None = None,
    git_push: bool | None = None,
    force_git: bool = False,
    min_git_interval_sec: float = 120.0,
) -> dict:
    """Rebuild catalog + status JSON. Optionally commit/push for live site.

    Public site is filtered to Saudi allowlist (SDAIA, TGA, MC, MEWA) so global
    gazette crawls never reappear. Set REGINTEL_FULL_CATALOG=1 to disable.

    During ministry discovery, pass ``ministry_progress`` (counts, pages_visited,
    discovery_methods) so the Crawl tab updates even when catalog PDF count is
    unchanged. Git also stages ``ministry_document_list.json``.
    """
    global _last_git_push, _last_catalog_count, _last_listed_count, _last_pages_seen

    manifest = load_manifest()
    catalog = build_catalog_from_manifest(manifest)
    catalog = _filter_public_catalog(catalog)
    status = build_status(
        phase=phase, message=message, current_source=current_source
    )
    # Status totals for the public site reflect published (filtered) catalog
    status["totals"]["pdfs"] = len(catalog)
    by_j = Counter((r.get("jurisdiction") or "Unknown") for r in catalog)
    status["totals"]["jurisdictions"] = len(by_j)
    status["by_jurisdiction"] = [
        {"jurisdiction": j, "count": c} for j, c in by_j.most_common(20)
    ]
    status["by_source_kind"] = (
        [{"source_kind": "ministry", "count": len(catalog)}] if catalog else []
    )
    if not message:
        status["message"] = f"Saudi ministries · {len(catalog)} PDFs"
    elif "catalog" in message.lower() and "total" in message.lower():
        status["message"] = f"Saudi ministries · {len(catalog)} PDFs"

    # Merge ministry discovery / download progress into crawl_status (public)
    listed = None
    pages_seen = None
    if ministry_progress:
        status["ministry_document_list"] = ministry_progress
        counts = ministry_progress.get("counts") or {}
        listed = counts.get("listed_total")
        pages_seen = ministry_progress.get("pages_visited")
        status["totals"]["ministry_listed"] = counts.get("listed_total", 0)
        status["totals"]["ministry_downloaded"] = counts.get("downloaded", 0)
        status["totals"]["ministry_failed"] = counts.get("download_failed", 0)
        status["totals"]["ministry_scanned"] = counts.get("scanned_pdf", 0)
        status["totals"]["ministry_to_download"] = counts.get("to_download", 0)
    elif current_source and current_source.get("listed") is not None:
        listed = current_source.get("listed")
        status["totals"]["ministry_listed"] = listed
        status["totals"]["ministry_downloaded"] = current_source.get("downloaded", 0)
        status["totals"]["ministry_failed"] = current_source.get("download_failed", 0)
        status["totals"]["ministry_scanned"] = current_source.get("scanned_pdf", 0)
        status["totals"]["ministry_to_download"] = current_source.get("to_download", 0)

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
    write_active_crawls(job_snapshot(status, current_source, ministry_progress))
    if ASSETS_CATALOG.parent.is_dir():
        ASSETS_CATALOG.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    n = len(catalog)
    listed_n = int(listed) if listed is not None else -1
    pages_n = int(pages_seen) if pages_seen is not None else -1
    progress_changed = (
        n != _last_catalog_count
        or (listed_n >= 0 and listed_n != _last_listed_count)
        or (pages_n >= 0 and pages_n != _last_pages_seen)
        or phase in ("discovering", "listed", "downloading", "complete")
    )

    do_git = git_push
    if do_git is None:
        do_git = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get(
            "REGINTEL_LIVE_GIT_PUSH"
        ) == "1"

    if do_git and (force_git or progress_changed):
        now = time.time()
        if force_git or (now - _last_git_push) >= min_git_interval_sec:
            label = status.get("phase") or phase
            if listed_n >= 0:
                label = f"{label}, listed={listed_n}"
            if _git_push_live(n, label):
                _last_git_push = now
                _last_catalog_count = n
                if listed_n >= 0:
                    _last_listed_count = listed_n
                if pages_n >= 0:
                    _last_pages_seen = pages_n

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
        # Snapshot this job before rebase so another site cannot overwrite it.
        our_job = None
        try:
            st = json.loads(WEB_STATUS.read_text(encoding="utf-8"))
            our_job = job_snapshot(st)
        except Exception:
            our_job = None

        # Always fetch latest main before commit to reduce non-fast-forward
        if remote:
            fr = _run_git(["fetch", remote, "main:refs/remotes/origin/main"], env=env)
            if fr.returncode != 0:
                print(f"[live-publish] fetch warn: {fr.stderr.strip()[:300]}", flush=True)
            _run_git(["rebase", "origin/main"], env=env)
        else:
            _run_git(["pull", "--rebase", "origin", "main"], env=env)

        # Rebase may have brought other sites' crawl files; restore ours, rebuild index.
        write_active_crawls(our_job)

        paths = [
            "data/pdfs/manifest.json",
            "data/pdfs/crawl_status.json",
            "web/data/pdfs_catalog.json",
            "web/data/crawl_status.json",
            "web/data/active_crawls.json",
            "web/data/ministry_document_list.json",
            "web/data/pdfs_coverage.json",
            "android/app/src/main/assets/pdfs_catalog.json",
        ]
        if WEB_CRAWLS_DIR.is_dir():
            for p in WEB_CRAWLS_DIR.glob("*.json"):
                paths.append(str(p.relative_to(ROOT)))
        for p in paths:
            if (ROOT / p).exists():
                _run_git(["add", "-f", p])
        # Per-ministry master lists (discovery progress)
        lists_dir = ROOT / "data" / "pdfs" / "ministry_lists"
        if lists_dir.is_dir():
            for p in lists_dir.glob("*.json"):
                _run_git(["add", "-f", str(p.relative_to(ROOT))])

        st = _run_git(["diff", "--staged", "--quiet"])
        if st.returncode == 0:
            return False  # nothing staged

        msg = f"chore: live crawl progress ({pdf_count} catalog pdfs, {phase}) {_now()}"
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
                print(
                    f"[live-publish] pushed progress ({pdf_count} catalog PDFs, {phase})",
                    flush=True,
                )
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
    # Preserve existing crawl phase/message when run as a post-step helper
    # (workflow used to overwrite real discovery status with "manual").
    prev_phase = "idle"
    prev_msg = "live publish"
    ministry_progress = None
    try:
        if WEB_STATUS.exists():
            prev = json.loads(WEB_STATUS.read_text(encoding="utf-8"))
            if prev.get("phase") and prev.get("phase") not in ("manual",):
                prev_phase = prev["phase"]
            if prev.get("message") and "manual" not in str(prev.get("message")).lower():
                prev_msg = prev["message"]
            if prev.get("ministry_document_list"):
                ministry_progress = prev["ministry_document_list"]
        list_path = WEB_DATA / "ministry_document_list.json"
        if list_path.exists():
            lst = json.loads(list_path.read_text(encoding="utf-8"))
            ministry_progress = {
                "label": lst.get("label") or "Saudi Arabia - SDAIA",
                "target_url": lst.get("target_url") or "https://sdaia.gov.sa",
                "counts": lst.get("counts") or {},
                "discovery_methods": lst.get("discovery_methods") or {},
                "pages_visited": lst.get("pages_visited"),
                "list_file": "data/ministry_document_list.json",
                "updated_at": lst.get("updated_at"),
            }
            c = lst.get("counts") or {}
            if lst.get("phase") in (
                "discovering",
                "listed",
                "downloading",
                "complete",
            ):
                prev_phase = lst["phase"] if prev_phase in ("idle", "manual") else prev_phase
            if c.get("listed_total") is not None and prev_msg in ("live publish", "manual live_publish"):
                prev_msg = (
                    f"{prev_phase}: listed={c.get('listed_total', 0)} "
                    f"downloaded={c.get('downloaded', 0)} "
                    f"failed={c.get('download_failed', 0)}"
                )
    except Exception:
        pass
    s = publish(
        phase=prev_phase,
        message=prev_msg,
        ministry_progress=ministry_progress,
        force_git=False,
    )
    print(json.dumps({"phase": s.get("phase"), "message": s.get("message"), "totals": s.get("totals")}, indent=2))

#!/usr/bin/env python3
"""
Eva batch summarizer: read PDFs (local or URL), produce summaries, write web index.

Resume-safe store:
  data/eva/summaries.jsonl   (one JSON object per line, keyed by id)
  web/data/eva_summaries.json (compact array for the site)

Usage:
  export XAI_API_KEY=...   # optional; without it uses extractive summaries
  .venv/bin/python collector/eva_summarize.py --limit 50
  .venv/bin/python collector/eva_summarize.py --jurisdiction "Saudi Arabia"
  .venv/bin/python collector/eva_summarize.py --only-missing --limit 100
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT))

from eva_extract import extract_for_record, looks_like_glyph_dump  # type: ignore
from eva_llm import get_client, is_placeholder_title, summarize_pdf_text  # type: ignore

EVA_DIR = ROOT / "data" / "eva"
SUMMARIES_JSONL = EVA_DIR / "summaries.jsonl"
WEB_SUMMARIES = ROOT / "web" / "data" / "eva_summaries.json"
CATALOG_CANDIDATES = [
    ROOT / "web" / "data" / "pdfs_catalog.json",
    ROOT / "data" / "pdfs" / "manifest.json",
]


def load_catalog() -> list[dict]:
    # Prefer enriched catalog
    path = ROOT / "web" / "data" / "pdfs_catalog.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    # Fall back to manifest downloads
    man = ROOT / "data" / "pdfs" / "manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        out = []
        for i, rec in enumerate(m.get("downloads") or []):
            if rec.get("dry_run"):
                continue
            out.append(
                {
                    "id": rec.get("sha256") or f"pdf_{i}",
                    "title": rec.get("title") or rec.get("url"),
                    "jurisdiction": rec.get("jurisdiction"),
                    "source_kind": rec.get("source_kind"),
                    "url": rec.get("url"),
                    "open_url": rec.get("url"),
                    "source_page": rec.get("source_page"),
                    "local_path": rec.get("path"),
                    "path": rec.get("path"),
                    "bytes": rec.get("bytes"),
                }
            )
        return out
    return []


def load_existing() -> dict[str, dict]:
    existing: dict[str, dict] = {}
    if SUMMARIES_JSONL.exists():
        for line in SUMMARIES_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("id"):
                existing[obj["id"]] = obj
    return existing


def append_summary(rec: dict) -> None:
    EVA_DIR.mkdir(parents=True, exist_ok=True)
    with SUMMARIES_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def rewrite_jsonl(all_summaries: dict[str, dict]) -> None:
    """Replace jsonl with one row per id so reprocess does not leave stale lines."""
    EVA_DIR.mkdir(parents=True, exist_ok=True)
    rows = list(all_summaries.values())
    rows.sort(key=lambda r: r.get("summarized_at") or "")
    with SUMMARIES_JSONL.open("w", encoding="utf-8") as f:
        for rec in rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def summary_is_glyph_junk(rec: dict) -> bool:
    blob = " ".join(
        [
            str(rec.get("summary") or ""),
            " ".join(rec.get("key_points") or []),
            " ".join(rec.get("topics") or []),
        ]
    )
    return looks_like_glyph_dump(blob)


def summary_is_weak(rec: dict) -> bool:
    """True when the stored summary is blanks, TOC dots, or a click-here dump."""
    import re

    summary = str(rec.get("summary") or "")
    title = str(rec.get("title") or "")
    if summary_is_glyph_junk(rec):
        return True
    if summary.lower().lstrip().startswith("click here"):
        return True
    if summary.count("_") >= 8 or re.search(r"_{5,}", summary):
        return True
    if re.search(r"\.{6,}\s*\d+", summary):
        return True
    if re.fullmatch(r"[\s\-–—._]+", summary or ""):
        return True
    return False


def publish_web(all_summaries: dict[str, dict], *, max_web: int = 5000) -> None:
    """Write compact summaries for the static site (newest first)."""
    rows = list(all_summaries.values())
    rows.sort(key=lambda r: r.get("summarized_at") or "", reverse=True)
    compact = []
    for r in rows[:max_web]:
        compact.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "jurisdiction": r.get("jurisdiction"),
                "source_kind": r.get("source_kind"),
                "url": r.get("url"),
                "open_url": r.get("open_url") or r.get("url"),
                "source_page": r.get("source_page"),
                "summary": r.get("summary"),
                "key_points": r.get("key_points") or [],
                "topics": r.get("topics") or [],
                "document_type": r.get("document_type"),
                "method": r.get("method"),
                "summarized_at": r.get("summarized_at"),
            }
        )
    WEB_SUMMARIES.parent.mkdir(parents=True, exist_ok=True)
    WEB_SUMMARIES.write_text(
        json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    meta = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(compact),
        "total_indexed": len(all_summaries),
        "llm_available": get_client() is not None,
    }
    (WEB_SUMMARIES.parent / "eva_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )


def main():
    p = argparse.ArgumentParser(description="Eva: summarize PDFs for RegIntel")
    p.add_argument("--limit", type=int, default=25, help="Max PDFs to process this run")
    p.add_argument("--jurisdiction", action="append", dest="jurisdictions", help="Filter (substring)")
    p.add_argument("--only-missing", action="store_true", default=True)
    p.add_argument("--reprocess", action="store_true", help="Re-summarize even if present")
    p.add_argument(
        "--fix-glyphs",
        action="store_true",
        help="Re-summarize rows whose text is /uniXXXX glyph dumps",
    )
    p.add_argument(
        "--fix-weak",
        action="store_true",
        help="Re-summarize form/TOC/click-here junk summaries",
    )
    p.add_argument("--max-pages", type=int, default=15, help="PDF pages to read per file")
    p.add_argument("--delay", type=float, default=0.4)
    p.add_argument("--publish-only", action="store_true", help="Only rebuild web JSON from jsonl")
    args = p.parse_args()

    existing = load_existing()
    if args.publish_only:
        publish_web(existing)
        print(f"Published {len(existing)} summaries → {WEB_SUMMARIES}")
        return

    catalog = load_catalog()
    print(f"Catalog size: {len(catalog)}; already summarized: {len(existing)}")
    print(f"LLM mode: {'SpaceXAI/xAI' if get_client() else 'extractive (no XAI_API_KEY)'}")

    broken_ids = set()
    if args.fix_glyphs:
        broken_ids = {i for i, r in existing.items() if summary_is_glyph_junk(r)}
        print(f"Glyph-junk summaries to rebuild: {len(broken_ids)}")
    if args.fix_weak:
        weak_ids = {i for i, r in existing.items() if summary_is_weak(r)}
        broken_ids |= weak_ids
        print(f"Weak (form/TOC/click-here) summaries to rebuild: {len(weak_ids)}")

    juris = [j.lower() for j in (args.jurisdictions or [])]
    todo = []
    by_id = {}
    for rec in catalog:
        rid = rec.get("id") or rec.get("sha256")
        if rid:
            by_id[rid] = rec
    # --fix-glyphs: start from existing rows so we still have URL/path if catalog dropped them
    source_rows = list(catalog)
    if args.fix_glyphs or args.fix_weak:
        extra = []
        for rid in broken_ids:
            if rid in by_id:
                rec = dict(by_id[rid])
            else:
                rec = dict(existing[rid])
            prev = existing.get(rid) or {}
            rec.setdefault("local_path", prev.get("local_path"))
            rec.setdefault("path", prev.get("path") or prev.get("local_path"))
            rec.setdefault("open_url", prev.get("open_url") or prev.get("url"))
            rec.setdefault("url", prev.get("url") or prev.get("open_url"))
            extra.append(rec)
        source_rows = extra
    for rec in source_rows:
        rid = rec.get("id") or rec.get("sha256")
        if not rid:
            continue
        if args.fix_glyphs or args.fix_weak:
            if rid not in broken_ids:
                continue
        elif not args.reprocess and rid in existing:
            continue
        if juris and not args.fix_glyphs and not args.fix_weak:
            j = (rec.get("jurisdiction") or "").lower()
            if not any(x in j for x in juris):
                continue
        # need a way to get bytes
        if not (rec.get("local_path") or rec.get("path") or rec.get("open_url") or rec.get("url")):
            continue
        todo.append(rec)

    # Prefer local files + Saudi ministries first
    def rank(r):
        j = (r.get("jurisdiction") or "").lower()
        lp = r.get("local_path") or r.get("path") or ""
        local = 0 if lp and (ROOT / lp).is_file() else 1
        saudi = 0 if "saudi" in j else 1
        return (local, saudi)

    todo.sort(key=rank)
    if args.limit and not args.fix_glyphs and not args.fix_weak:
        todo = todo[: args.limit]

    print(f"Processing {len(todo)} PDFs…")
    ok = fail = 0
    for i, rec in enumerate(todo, 1):
        rid = rec.get("id") or rec.get("sha256")
        title = rec.get("title") or rid
        print(f"[{i}/{len(todo)}] {title[:80]}")
        try:
            text = extract_for_record(rec, max_pages=args.max_pages)
            s = summarize_pdf_text(
                title=title,
                jurisdiction=rec.get("jurisdiction") or "",
                url=rec.get("open_url") or rec.get("url") or "",
                text=text,
            )
            nice_title = s.get("display_title") or title
            if is_placeholder_title(title) and nice_title:
                title = nice_title
            out = {
                "id": rid,
                "title": title,
                "jurisdiction": rec.get("jurisdiction"),
                "source_kind": rec.get("source_kind"),
                "url": rec.get("url"),
                "open_url": rec.get("open_url") or rec.get("url"),
                "source_page": rec.get("source_page"),
                "local_path": rec.get("local_path") or rec.get("path"),
                "summary": s.get("summary"),
                "key_points": s.get("key_points") or [],
                "topics": s.get("topics") or [],
                "document_type": s.get("document_type"),
                "method": s.get("method"),
                "text_chars": len(text),
                "summarized_at": datetime.now(timezone.utc).isoformat(),
            }
            append_summary(out)
            existing[rid] = out
            ok += 1
            print(f"  ok method={out['method']} chars={out['text_chars']}")
        except Exception as e:
            fail += 1
            print(f"  FAIL: {e}")
            err = {
                "id": rid,
                "title": title,
                "jurisdiction": rec.get("jurisdiction"),
                "url": rec.get("open_url") or rec.get("url"),
                "summary": f"Eva could not read this PDF: {e}",
                "key_points": [],
                "topics": [],
                "document_type": "error",
                "method": "error",
                "error": str(e)[:300],
                "summarized_at": datetime.now(timezone.utc).isoformat(),
            }
            # don't mark permanent failure as success for resume — skip writing errors as done
            # unless --reprocess won't help; store error so we can skip retries optionally
            # For now skip append so --only-missing retries later
        time.sleep(args.delay)
        if i % 10 == 0:
            publish_web(existing)

    if args.fix_glyphs or args.fix_weak or args.reprocess:
        rewrite_jsonl(existing)
    publish_web(existing)
    print(json.dumps({"ok": ok, "fail": fail, "total_summaries": len(existing)}, indent=2))
    print(f"Web index: {WEB_SUMMARIES}")


if __name__ == "__main__":
    main()

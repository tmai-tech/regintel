#!/usr/bin/env python3
"""Index local gazette PDF downloads into Firestore + web/data for the app.

Enriches each PDF with lawyer-useful filter fields:
  jurisdiction, law_type, year (latest update), source_kind, language,
  host, filename pattern signals, source_page URL, byte size.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "pdfs" / "manifest.json"
GAZETTE = ROOT / "data" / "gazette.json"
WEB_CATALOG = ROOT / "web" / "data" / "pdfs_catalog.json"
ASSETS_CATALOG = ROOT / "android" / "app" / "src" / "main" / "assets" / "pdfs_catalog.json"
COVERAGE_JSON = ROOT / "data" / "pdfs" / "coverage_report.json"
WEB_COVERAGE = ROOT / "web" / "data" / "pdfs_coverage.json"

YEAR_RE = re.compile(r"(?:19|20)\d{2}")

# (regex, law_type) — first match wins; ordered most-specific first
LAW_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"amend(?:ment|ing|ed)?|\bamdt\b|const\.?\s*amend", re.I), "amendment"),
    (re.compile(r"white[-\s]?paper|green[-\s]?paper|consultation", re.I), "consultation_paper"),
    (re.compile(r"committee|standing.?committee|\bscr\b|report.?summary|pac[-_]", re.I), "committee_report"),
    (re.compile(r"statutory\s*instrument|\bsi[-_\s]?\d|regulation|regulat(?:ory)|decree|arrêté|decreto", re.I), "regulation"),
    (re.compile(r"\bordinance\b|\bord\d|\bordinance\b", re.I), "ordinance"),
    (re.compile(r"\bbill\b|wetsvoorstel|projet\s+de\s+loi|proposition\s+de\s+loi|projeto\s+de\s+lei|l17b\d", re.I), "bill"),
    (re.compile(r"\bact\b|\bstatute\b|gesetz|loi\b|legge|ley\b|ustawa", re.I), "act"),
    (re.compile(r"constitution|const\.?\s*amend", re.I), "constitutional"),
    (re.compile(r"gazette|cong-bao|bgbl|official.?journal|monitorul|uradni.?list|federal.?register", re.I), "gazette"),
    (re.compile(r"notice|notification|oath|appointment", re.I), "notice"),
    (re.compile(r"resolution|resolu", re.I), "resolution"),
    (re.compile(r"calendar|schedule|directory|handbuch|statuut|standing.?orders|accessibility|privacy|polityka", re.I), "procedural"),
    (re.compile(r"plenarprotokoll|official.?report|hansard|oj[-_]|agenda", re.I), "parliamentary_record"),
]

# Default language by jurisdiction (ISO 639-1-ish label for filters)
JURISDICTION_LANG: dict[str, str] = {
    "USA Federal": "en",
    "New York": "en",
    "Delaware": "en",
    "California": "en",
    "UK": "en",
    "Australia": "en",
    "Singapore": "en",
    "Hong Kong": "en",
    "India": "en",
    "New Zealand": "en",
    "Canada Federal": "en",
    "British Columbia": "en",
    "Ontario": "en",
    "Manitoba": "en",
    "Cayman Islands": "en",
    "Ireland": "en",
    "Malta": "en",
    "Philippines": "en",
    "European Union": "en",
    "France": "fr",
    "Belgium": "nl",
    "Luxembourg": "fr",
    "Switzerland": "de",
    "Germany": "de",
    "Austria": "de",
    "Poland": "pl",
    "Portugal": "pt",
    "Romania": "ro",
    "Slovenia": "sl",
    "Finland": "fi",
    "Turkey": "tr",
    "Taiwan": "zh",
    "Vietnam": "vi",
    "UAE": "ar",
    "Spain": "es",
    "Mexico": "es",
    "Chile": "es",
    "Colombia": "es",
    "Peru": "es",
    "Costa Rica": "es",
    "Brazil": "pt",
    "Italy": "it",
    "Netherlands": "nl",
    "Sweden": "sv",
    "Norway": "no",
    "Denmark": "da",
    "Greece": "el",
    "Czech Republic": "cs",
    "Slovakia": "sk",
    "Hungary": "hu",
    "Japan": "ja",
    "South Korea": "ko",
    "China": "zh",
    "Thailand": "th",
    "Indonesia": "id",
    "Malaysia": "ms",
    "Israel": "he",
    "Saudi Arabia": "ar",
    "Qatar": "ar",
    "Egypt": "ar",
    "Bulgaria": "bg",
    "Croatia": "hr",
    "Cyprus": "el",
    "Estonia": "et",
    "Iceland": "is",
    "Latvia": "lv",
    "Lithuania": "lt",
}


def infer_law_type(title: str, filename: str, url: str, source_kind: str | None) -> str:
    blob = f"{title or ''} {filename or ''} {url or ''}"
    for pat, kind in LAW_PATTERNS:
        if pat.search(blob):
            return kind
    if source_kind == "official_gazette":
        return "gazette"
    if source_kind == "parliamentary_bills":
        return "bill"
    if source_kind == "legal_databases":
        return "statute_database"
    return "other"


def infer_years(title: str, filename: str, url: str, downloaded_at: str | None) -> list[int]:
    blob = f"{title or ''} {filename or ''} {url or ''}"
    years = sorted(
        {int(y) for y in YEAR_RE.findall(blob) if 1990 <= int(y) <= 2035},
        reverse=True,
    )
    if not years and downloaded_at:
        try:
            years = [int(str(downloaded_at)[:4])]
        except (TypeError, ValueError):
            pass
    return years


def infer_language(jurisdiction: str | None, title: str, filename: str) -> str:
    blob = f"{title or ''} {filename or ''}".lower()
    if re.search(r"\b(hindi|_hi\b|हि)", blob):
        return "hi"
    if re.search(r"_en\b|/en/|\ben\.pdf|english", blob):
        return "en"
    if re.search(r"_fr\b|/fr/|fran[cç]", blob):
        return "fr"
    if re.search(r"_de\b|/de/|deutsch", blob):
        return "de"
    if re.search(r"_nl\b|/nl/|nederlands", blob):
        return "nl"
    return JURISDICTION_LANG.get(jurisdiction or "", "und")


def filename_signals(filename: str) -> list[str]:
    """Lightweight tags for search/filter (bill numbers, gazette issue codes)."""
    name = filename or ""
    tags: list[str] = []
    if re.search(r"Bill\d+of\d{4}", name, re.I):
        tags.append("bill_number")
    if re.search(r"Ord\d+of\d{4}", name, re.I):
        tags.append("ordinance_number")
    if re.search(r"^\d{4}-\d+\.pdf$", name, re.I):
        tags.append("fr_document_number")  # Federal Register style
    if re.search(r"^D\d{10,}\.pdf$", name, re.I):
        tags.append("pl_isap_id")
    if re.search(r"^[urm]\d{7}\.pdf$", name, re.I):
        tags.append("si_uradni_list")
    if re.search(r"FC-Official-Report|OFCR-|PAC-", name, re.I):
        tags.append("hansard_or_committee")
    if re.search(r"parl-\d+of\d{4}", name, re.I):
        tags.append("sg_parl_bill")
    return tags


_PLACEHOLDER_TITLE = re.compile(
    r"^(embedded[\s_-]?url|clicke?\s*here(?:\s+to\b.*)?|show|here|link|download|"
    r"view|تنزيل|هنا|اضغط\s*هنا.*)$",
    re.I | re.U,
)
_DISCOVERY_METHODS = frozenset(
    {
        "embedded-url",
        "href",
        "script",
        "sitemap",
        "seed_list",
        "playwright_net",
        "nav_api",
        "json_api",
        "embed",
        "direct",
    }
)


def pretty_filename(name: str) -> str:
    raw = unquote(str(name or "")).strip()
    raw = raw.split("?")[0].split("#")[0]
    raw = raw.rsplit("/", 1)[-1]
    raw = re.sub(r"(?i)\.pdf$", "", raw)
    raw = re.sub(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[_-]*",
        "",
        raw,
        flags=re.I,
    )
    raw = raw.replace("_", " ").replace("-", " ")
    raw = re.sub(r"\s+", " ", raw).strip(" ._-")
    return raw


def is_placeholder_title(title: str) -> bool:
    t = re.sub(r"[\s\u200b\u200c\u200d\ufeff]+", " ", str(title or "")).strip()
    if not t:
        return True
    if t.lower() in _DISCOVERY_METHODS:
        return True
    if t.lower().startswith("http://") or t.lower().startswith("https://"):
        return True
    if _PLACEHOLDER_TITLE.match(t):
        return True
    if len(t) < 3:
        return True
    return False


def display_title(rec: dict, index: int = 0) -> str:
    filename = rec.get("filename") or ""
    if not filename:
        path = rec.get("path") or rec.get("local_path") or ""
        filename = Path(path).name if path else ""
    url = rec.get("open_url") or rec.get("url") or rec.get("download_url") or ""
    raw = rec.get("title") or ""
    if raw and not is_placeholder_title(raw):
        return str(raw).strip()
    for cand in (pretty_filename(filename), pretty_filename(url)):
        if cand and not is_placeholder_title(cand):
            return cand
    return filename or pretty_filename(url) or f"PDF {index + 1}"


def _site_code(jurisdiction: str | None, url: str, host: str) -> str:
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from saudi_ministry_allowlist import site_code_for  # type: ignore
    except Exception:
        return ""
    return site_code_for(
        {"jurisdiction": jurisdiction or "", "url": url or "", "host": host or ""}
    ) or ""


def enrich_record(rec: dict, index: int) -> dict:
    local = ROOT / (rec.get("path") or "")
    size = rec.get("bytes") or (local.stat().st_size if local.is_file() else 0)
    filename = local.name if rec.get("path") else (
        rec.get("filename") or pretty_filename(rec.get("url") or "") or f"doc_{index}.pdf"
    )
    if not str(filename).lower().endswith(".pdf") and rec.get("url"):
        guessed = Path(unquote(urlparse(rec.get("url") or "").path)).name
        if guessed:
            filename = guessed
    title = display_title({**rec, "filename": filename}, index)
    url = rec.get("url") or ""
    open_url = rec.get("download_url") or url
    jurisdiction = rec.get("jurisdiction")
    source_kind = rec.get("source_kind")
    years = infer_years(title, filename, url, rec.get("downloaded_at"))
    year = years[0] if years else None
    host = ""
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        host = ""

    return {
        "id": rec.get("sha256") or f"pdf_{index}",
        "title": title,
        "filename": filename,
        "jurisdiction": jurisdiction,
        "site_code": _site_code(jurisdiction, url, host),
        "source_kind": source_kind,
        "law_type": infer_law_type(title, filename, url, source_kind),
        "year": year,
        "years": years,
        "language": infer_language(jurisdiction, title, filename),
        "status": "downloaded",
        "host": host,
        "filename_tags": filename_signals(filename),
        "source_page": rec.get("source_page"),
        "url": url,
        "open_url": open_url,
        "download_url": rec.get("download_url"),
        "bytes": size,
        "sha256": rec.get("sha256"),
        "downloaded_at": rec.get("downloaded_at"),
        "local_path": rec.get("path"),
    }


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text or "unknown", flags=re.U)
    s = re.sub(r"[-\s]+", "_", s.strip()).strip("_")
    return s[:80] or "unknown"


def build_coverage(catalog: list[dict], manifest: dict) -> dict:
    """Per-jurisdiction coverage vs gazette source list for gap reporting."""
    gazette = []
    if GAZETTE.exists():
        gazette = json.loads(GAZETTE.read_text(encoding="utf-8"))

    by_j: dict[str, list[dict]] = defaultdict(list)
    for item in catalog:
        by_j[item.get("jurisdiction") or "Unknown"].append(item)

    law_type_counts = Counter(i.get("law_type") for i in catalog)
    year_counts = Counter(i.get("year") for i in catalog if i.get("year"))
    kind_counts = Counter(i.get("source_kind") for i in catalog)

    sites = []
    zero = []
    partial = []
    ok = []
    for row in gazette:
        j = row.get("jurisdiction") or "Unknown"
        items = by_j.get(j, [])
        kinds_have = sorted({i.get("source_kind") for i in items if i.get("source_kind")})
        expected_kinds = []
        if row.get("parliamentary_bills"):
            expected_kinds.append("parliamentary_bills")
        if row.get("official_gazette"):
            expected_kinds.append("official_gazette")
        missing_kinds = [k for k in expected_kinds if k not in kinds_have]
        n = len(items)
        if n == 0:
            level = "zero"
            zero.append(j)
        elif n < 3 or missing_kinds:
            level = "partial"
            partial.append(j)
        else:
            level = "ok"
            ok.append(j)
        years = sorted({i.get("year") for i in items if i.get("year")}, reverse=True)
        law_types = sorted({i.get("law_type") for i in items if i.get("law_type")})
        sites.append(
            {
                "jurisdiction": j,
                "pdf_count": n,
                "coverage": level,
                "source_kinds_present": kinds_have,
                "source_kinds_expected": expected_kinds,
                "source_kinds_missing": missing_kinds,
                "years": years,
                "law_types": law_types,
                "parliamentary_bills_url": row.get("parliamentary_bills") or None,
                "official_gazette_url": row.get("official_gazette") or None,
                "legal_databases_url": row.get("legal_databases") or None,
            }
        )

    errors = manifest.get("errors") or []
    err_hosts: Counter[str] = Counter()
    for e in errors:
        try:
            h = urlparse(e.get("url") or "").netloc.lower().removeprefix("www.")
            if h:
                err_hosts[h] += 1
        except Exception:
            pass

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_generated_at": manifest.get("generated_at"),
        "totals": {
            "gazette_jurisdictions": len(gazette),
            "pdfs": len(catalog),
            "coverage_zero": len(zero),
            "coverage_partial": len(partial),
            "coverage_ok": len(ok),
            "manifest_errors": len(errors),
        },
        "law_type_counts": dict(law_type_counts.most_common()),
        "year_counts": {str(k): v for k, v in sorted(year_counts.items(), reverse=True)},
        "source_kind_counts": dict(kind_counts.most_common()),
        "zero_jurisdictions": zero,
        "partial_jurisdictions": partial,
        "ok_jurisdictions": ok,
        "top_error_hosts": [{"host": h, "count": c} for h, c in err_hosts.most_common(25)],
        "sites": sites,
    }


def init(sa_path: str | None):
    import firebase_admin
    from firebase_admin import credentials, firestore

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
    catalog = [enrich_record(rec, i) for i, rec in enumerate(downloads)]

    # Sort newest first when possible
    catalog.sort(key=lambda x: x.get("downloaded_at") or "", reverse=True)

    for path in (WEB_CATALOG, ASSETS_CATALOG):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {path} ({len(catalog)} items)")

    coverage = build_coverage(catalog, manifest)
    for path in (COVERAGE_JSON, WEB_COVERAGE):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(coverage, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {path}")

    t = coverage["totals"]
    print(
        f"Coverage: {t['pdfs']} PDFs across "
        f"{t['coverage_ok']} ok / {t['coverage_partial']} partial / "
        f"{t['coverage_zero']} zero of {t['gazette_jurisdictions']} jurisdictions"
    )
    print("Law types:", coverage["law_type_counts"])
    print("Years:", coverage["year_counts"])

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
            "law_type_counts": coverage["law_type_counts"],
            "year_counts": coverage["year_counts"],
            "coverage_zero": t["coverage_zero"],
            "coverage_partial": t["coverage_partial"],
            "coverage_ok": t["coverage_ok"],
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

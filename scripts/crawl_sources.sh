#!/usr/bin/env bash
# Full-site BFS PDF crawl (colleague Extraction_Script strategy).
#
# Usage:
#   scripts/crawl_sources.sh --max-pages 500
#   scripts/crawl_sources.sh --jurisdiction "USA Federal" --max-pages 300
#   scripts/crawl_sources.sh --url-only --url "https://example.gov" --label Ex --max-pages 200
#   scripts/crawl_sources.sh --dry-run --url-only --url "https://example.gov" --max-pages 50
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
fi

SEED=0
INDEX=1
LAWS=0
DRY=0
URL_ONLY=0
INCLUDE_LEGAL=0
NO_PLAYWRIGHT=0
MAX_PDFS=0
MAX_PAGES=500
DELAY=0.4
LABEL="AdHoc"
KIND="custom"
URLS=()
JURIS=()
FROM_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED=1; shift ;;
    --no-index) INDEX=0; shift ;;
    --laws) LAWS=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --url-only) URL_ONLY=1; shift ;;
    --include-legal-db) INCLUDE_LEGAL=1; shift ;;
    --no-playwright) NO_PLAYWRIGHT=1; shift ;;
    --max|--max-pdfs-per-source) MAX_PDFS="$2"; shift 2 ;;
    --max-pages) MAX_PAGES="$2"; shift 2 ;;
    --delay) DELAY="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --kind) KIND="$2"; shift 2 ;;
    --url) URLS+=("$2"); shift 2 ;;
    --from-file) FROM_FILE="$2"; shift 2 ;;
    --jurisdiction|-j) JURIS+=("$2"); shift 2 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "=== RegIntel full-site PDF crawl ==="
echo "python=$PY max_pages=$MAX_PAGES max_pdfs_per_source=$MAX_PDFS (0=unlimited)"

if [[ "$SEED" -eq 1 ]]; then
  echo "--- seed Excel ---"
  "$PY" scripts/seed_from_excel.py
fi

ARGS=(
  collector/download_gazette_pdfs.py
  --max-pages "$MAX_PAGES"
  --max-pdfs-per-source "$MAX_PDFS"
  --delay "$DELAY"
  --label "$LABEL"
  --kind "$KIND"
)
for j in "${JURIS[@]+"${JURIS[@]}"}"; do ARGS+=(--jurisdiction "$j"); done
for u in "${URLS[@]+"${URLS[@]}"}"; do ARGS+=(--url "$u"); done
[[ -n "$FROM_FILE" ]] && ARGS+=(--from-file "$FROM_FILE")
[[ "$URL_ONLY" -eq 1 ]] && ARGS+=(--url-only)
[[ "$INCLUDE_LEGAL" -eq 1 ]] && ARGS+=(--include-legal-db)
[[ "$NO_PLAYWRIGHT" -eq 1 ]] && ARGS+=(--no-playwright)
[[ "$DRY" -eq 1 ]] && ARGS+=(--dry-run)

echo "--- crawl (BFS + Playwright fallback) ---"
"$PY" "${ARGS[@]}"

if [[ "$DRY" -eq 1 ]]; then
  echo "Dry-run only."
  exit 0
fi

if [[ "$INDEX" -eq 1 ]]; then
  echo "--- rebuild PDF catalog ---"
  "$PY" collector/index_pdfs_firestore.py --skip-firestore
fi
if [[ "$LAWS" -eq 1 ]]; then
  "$PY" scripts/build_laws_catalog.py
fi

echo "=== done ==="
echo "PDFs:     data/pdfs/"
echo "Manifest: data/pdfs/manifest.json"
echo "Log:      data/pdfs/crawl_log.txt"

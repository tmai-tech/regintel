#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LIMIT="${1:-50}"
python collector/run_daily.py --limit "$LIMIT" --force
python collector/upload_firestore.py --only updates
python collector/upload_firestore.py --only meta

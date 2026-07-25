#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_ID="1:768748224321:android:6646eb31cbd2270e0fabc0"
PROJECT="roomcraft-e1312"
OUT="android/app/google-services.json"

if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
  if [ -f .secrets/roomcraft-e1312-firebase-adminsdk-fbsvc.json ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$ROOT/.secrets/roomcraft-e1312-firebase-adminsdk-fbsvc.json"
  fi
fi

TMP="$(mktemp)"
npx --yes firebase-tools@15 apps:sdkconfig ANDROID "$APP_ID" \
  --project "$PROJECT" --out "$TMP"
cp "$TMP" "$OUT"
rm -f "$TMP"
echo "Wrote $OUT"

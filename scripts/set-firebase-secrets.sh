#!/usr/bin/env bash
# Usage:
#   ./scripts/set-firebase-secrets.sh \
#     --app-id '1:768748224321:android:6646eb31cbd2270e0fabc0' \
#     --service-account ./.secrets/roomcraft-e1312-firebase-adminsdk-fbsvc.json \
#     [--groups testers] \
#     [--repo tmai-tech/regintel]
set -euo pipefail

REPO="tmai-tech/regintel"
APP_ID=""
SA_FILE=""
GROUPS="testers"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id) APP_ID="$2"; shift 2 ;;
    --service-account) SA_FILE="$2"; shift 2 ;;
    --groups) GROUPS="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$APP_ID" || -z "$SA_FILE" ]]; then
  echo "Required: --app-id and --service-account" >&2
  exit 1
fi
if [[ ! -f "$SA_FILE" ]]; then
  echo "Service account file not found: $SA_FILE" >&2
  exit 1
fi

gh secret set FIREBASE_ANDROID_APP_ID --repo "$REPO" --body "$APP_ID"
gh secret set FIREBASE_SERVICE_ACCOUNT --repo "$REPO" < "$SA_FILE"
gh secret set FIREBASE_TESTER_GROUPS --repo "$REPO" --body "$GROUPS"

echo "Secrets set on $REPO:"
gh secret list --repo "$REPO" | grep FIREBASE || true
echo "Done. Re-run: gh workflow run 'Build APK' --repo $REPO --ref main"

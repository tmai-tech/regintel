# RegIntel

BCI regulatory / legal-act intelligence: **Python collector** + **Kotlin Android app** on **Firebase App Distribution** (same pattern as [RoomCraft](https://github.com/tmai-tech/RoomCraft)).

## Firebase App Tester

| Item | Value |
|------|--------|
| Firebase project | `roomcraft-e1312` |
| Package | `com.logicrequire.regintel` |
| App ID | `1:768748224321:android:6646eb31cbd2270e0fabc0` |
| Install | Firebase App Tester invite / [App Distribution console](https://console.firebase.google.com/project/roomcraft-e1312/appdistribution) |

See [docs/FIREBASE_APP_DISTRIBUTION.md](docs/FIREBASE_APP_DISTRIBUTION.md).

## Architecture

```
Python collector (daily CI)
    → JSON in data/
    → Firestore collections regintel_*
Kotlin app (Compose)
    → reads Firestore (fallback: bundled assets)
    → detailed tables: Tracking / Primary / Updates / Gazette / Secondary
CI Build APK
    → Firebase App Distribution → App Tester
```

## Local Android build

```bash
# JDK 17 + Android SDK required
cd android
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/
```

## Python collector + Firestore seed

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
export GOOGLE_APPLICATION_CREDENTIALS=.secrets/roomcraft-e1312-firebase-adminsdk-fbsvc.json

.venv/bin/python scripts/seed_from_excel.py
.venv/bin/python collector/run_daily.py --limit 40 --force
.venv/bin/python collector/upload_firestore.py   # full catalog to Firestore
```

## CI

| Workflow | Purpose |
|----------|---------|
| **Build APK** | Debug APK → artifact + Firebase App Distribution |
| **Daily collector** | Fetch sources → Firestore updates → commit JSON |

## GitHub

https://github.com/tmai-tech/regintel

## Gazette bill / amendment PDFs

Scrape the **Gazette & Parliament Bills** links from the tracking plan and download PDFs:

```bash
.venv/bin/python collector/download_gazette_pdfs.py
# or pilot:
.venv/bin/python collector/download_gazette_pdfs.py --jurisdiction India --jurisdiction "USA Federal"
```

PDFs land in `data/pdfs/<jurisdiction>/…` with inventory in `data/pdfs/manifest.json`.  
See [docs/GAZETTE_PDF_COLLECTOR.md](docs/GAZETTE_PDF_COLLECTOR.md).


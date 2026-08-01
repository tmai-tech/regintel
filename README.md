# RegIntel

BCI regulatory / legal-act intelligence: **Python collector** + **Kotlin Android app** on **Firebase App Distribution** + **iOS-friendly web UI** on GitHub Pages (same Firebase pattern as [RoomCraft](https://github.com/tmai-tech/RoomCraft)).

## Get the app

| Platform | How |
|----------|-----|
| **iPhone / any browser** | **https://tmai-tech.github.io/regintel/** — open in Safari; optional Share → **Add to Home Screen**. See [docs/IOS_WEB.md](docs/IOS_WEB.md). |
| **Android** | Firebase App Tester invite (native APK). See [docs/FIREBASE_APP_DISTRIBUTION.md](docs/FIREBASE_APP_DISTRIBUTION.md). |

### Firebase App Tester (Android)

| Item | Value |
|------|--------|
| Firebase project | `roomcraft-e1312` |
| Package | `com.logicrequire.regintel` |
| App ID | `1:768748224321:android:6646eb31cbd2270e0fabc0` |
| Install | Firebase App Tester invite / [App Distribution console](https://console.firebase.google.com/project/roomcraft-e1312/appdistribution) |

### iOS web (Track 1)

| Item | Value |
|------|--------|
| Public URL | https://tmai-tech.github.io/regintel/ |
| Source | `web/` |
| Deploy | push to `main` (`web/**` or `data/**`) or `gh workflow run "Deploy UI to GitHub Pages"` |

## Architecture

```
Python collector (daily CI)
    → JSON in data/ (+ web/data/pdfs_catalog.json, laws_catalog.json)
    → scripts/build_laws_catalog.py (country, federal/state, summaries, authorities)
    → Firestore collections regintel_* (incl. regintel_laws)
Kotlin app (Compose) — Android
    → Laws + PDFs tabs; Firestore first, bundled assets fallback
    → Firebase App Distribution
Web UI (GitHub Pages) — iPhone & desktop
    → Laws tab: filter country / federal·state / law area / type + name search
    → PDFs tab: bill & amendment catalog
    → deploy-pages.yml from git
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
.venv/bin/python scripts/build_laws_catalog.py    # enriched laws for web + Android
.venv/bin/python collector/upload_firestore.py   # full catalog to Firestore (incl. regintel_laws)
```

## CI

| Workflow | Purpose |
|----------|---------|
| **Build APK** | Debug APK → artifact + Firebase App Distribution |
| **Deploy UI to GitHub Pages** | Publish `web/` → https://tmai-tech.github.io/regintel/ |
| **Daily collector** | Fetch sources → Firestore updates → commit JSON |
| **Crawl gazette PDFs** | Full-site BFS on GitHub Actions (resume-safe 4–6h chunks) → live catalog + **Crawl** tab |

## GitHub

https://github.com/tmai-tech/regintel

## Gazette bill / amendment PDFs (full-site BFS crawl)

Extraction follows the colleague **`Extraction_Script.py`** model:

1. **BFS same-site crawl** of each source URL (not just the landing page)  
2. **HTTP first**, automatic **Playwright** fallback for JS shells  
3. Collect every **`.pdf`**, download with resume + hash dedupe  

```bash
# Install optional JS engine (recommended once)
.venv/bin/pip install playwright && .venv/bin/playwright install chromium

# Full path: seed Excel → crawl all gazette links → rebuild catalog
scripts/crawl_sources.sh --seed --max-pages 500 --max 0

# Deep crawl (like colleague MAX_PAGES=2000)
scripts/crawl_sources.sh --max-pages 2000 --max 0

# Test any future link (dry-run = discover only)
scripts/crawl_sources.sh --url-only --dry-run --max-pages 100 \
  --url "https://example.gov/bills" --label "Example"

# Direct Python
.venv/bin/python collector/download_gazette_pdfs.py --max-pages 500 --max-pdfs-per-source 0
.venv/bin/python collector/index_pdfs_firestore.py --skip-firestore
```

PDFs land in `data/pdfs/<jurisdiction>/…` with inventory in `data/pdfs/manifest.json`.

| Doc | Purpose |
|------|---------|
| [docs/ADDING_SOURCES.md](docs/ADDING_SOURCES.md) | **Add new links → crawl checklist** (colleagues) |
| [docs/GAZETTE_PDF_COLLECTOR.md](docs/GAZETTE_PDF_COLLECTOR.md) | Collector internals, caps, coverage notes |


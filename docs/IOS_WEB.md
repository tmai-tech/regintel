# RegIntel on iPhone (web — Track 1)

iOS users get RegIntel **without a native App Store / TestFlight build** by using the
GitHub Pages web app. It is deployed automatically from git.

## Share this URL

| Item | Value |
|------|--------|
| **Public URL** | **https://tmai-tech.github.io/regintel/** |
| Repo | https://github.com/tmai-tech/regintel |
| Deploy workflow | `.github/workflows/deploy-pages.yml` |
| Source tree | `web/` |

Send testers the public URL (iMessage, email, Slack). No Firebase App Tester invite is required for iOS on this track.

## How testers open it on iPhone

1. Open **https://tmai-tech.github.io/regintel/** in **Safari** (Chrome works too; Safari is best for home screen).
2. Optional — install like an app:
   - Tap the **Share** button
   - **Add to Home Screen**
   - Confirm **Add**
3. Use search + jurisdiction filter; tap **Open PDF** or **Source page** (opens in Safari / PDF viewer).

Links on each card are real `<a href>` links (tap targets sized for fingers).

## What updates when

| Change | Result |
|--------|--------|
| Push to `main` under `web/**` or `data/**` | **Deploy UI to GitHub Pages** runs |
| Manual run | `gh workflow run "Deploy UI to GitHub Pages" --repo tmai-tech/regintel` |
| `pdfs_catalog.json` refreshed in `web/data/` | List content updates after the next Pages deploy |

The deploy job copies `data/*.json` into `web/data/` before publishing. Keep
`web/data/pdfs_catalog.json` generated via:

```bash
.venv/bin/python collector/index_pdfs_firestore.py
# or your usual PDF index path that writes web/data/pdfs_catalog.json
```

## Local preview

```bash
# from repo root
python3 -m http.server 8080 --directory web
# open http://127.0.0.1:8080/  (phone on same LAN: http://<your-ip>:8080/)
```

## Android vs iOS (current product split)

| Platform | How testers get the app |
|----------|-------------------------|
| **Android** | Firebase App Distribution (native APK) — see [FIREBASE_APP_DISTRIBUTION.md](./FIREBASE_APP_DISTRIBUTION.md) |
| **iOS** | This web URL (Safari / Home Screen) |

Native iOS (Track 2: SwiftUI + TestFlight / Firebase iOS) is intentionally deferred.

## Limitations (honest)

- Not a full offline native app; needs network to load the catalog and open PDFs.
- PDF rendering is the **browser’s** viewer (usually excellent on iOS Safari).
- Home Screen “app” has no push notifications.
- If a source blocks hotlinking, **Open PDF** may fail in the browser (same as many web clients).

## One-time GitHub Pages check

If the URL 404s:

1. Repo **Settings → Pages**
2. Build and deployment: **GitHub Actions**
3. Re-run **Deploy UI to GitHub Pages**

Console API should report `html_url`: `https://tmai-tech.github.io/regintel/`.

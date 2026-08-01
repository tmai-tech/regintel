# Gazette / Bill PDF collector

**Code crawls the sites** (not a human), using the same full-site BFS strategy as the colleague **`Extraction_Script.py`**.

For a short “add link → crawl → catalog” checklist, see **[ADDING_SOURCES.md](ADDING_SOURCES.md)**.

### Architecture

| Module | Role |
|--------|------|
| `Extraction_Script.py` | Colleague reference: BFS + requests + Playwright |
| `collector/site_crawler.py` | Production BFS crawler (same strategy) |
| `collector/download_gazette_pdfs.py` | Runs crawler on every gazette / `--url` source, downloads PDFs |
| `collector/site_adapters.py` | Optional API boosts (Federal Register, UK Bills, …) |

Each source URL is crawled **site-wide** (same domain, up to `--max-pages`), not just the landing page.

## Script

```bash
# All jurisdictions (resume-safe; skips already-downloaded URLs/hashes)
# Default cap is 500 PDFs per source URL (was 40 — that under-harvested large sites).
.venv/bin/python collector/download_gazette_pdfs.py

# Deep harvest of high-volume sites (Federal Register alone can expose 300–1000+ PDFs)
.venv/bin/python collector/download_gazette_pdfs.py \
  --jurisdiction "USA Federal" \
  --jurisdiction "UK" \
  --jurisdiction "India" \
  --max-pdfs-per-source 0 \
  --max-follow-pages 120 \
  --max-list-pages 25

# One or more jurisdictions
.venv/bin/python collector/download_gazette_pdfs.py \
  --jurisdiction "India" \
  --jurisdiction "USA Federal" \
  --max-pdfs-per-source 300

# Discover only (no files written) — use to measure real inventory per site
.venv/bin/python collector/download_gazette_pdfs.py --dry-run --max-pdfs-per-source 0

# Also crawl legal_databases column
.venv/bin/python collector/download_gazette_pdfs.py --include-legal-db

# JS-heavy / bot-blocked landing pages
.venv/bin/python collector/download_gazette_pdfs.py --playwright
```

## Columns used

| Column | `source_kind` folder |
|--------|----------------------|
| Parliamentary Bills | `parliamentary_bills/` |
| Official Gazette / Legal Publications | `official_gazette/` |
| Relevant Legal Databases (opt-in) | `legal_databases/` |

Multiple URLs in one cell (separated by `;`) are all visited.

## Output layout

```
data/pdfs/
  manifest.json                 # inventory of every download + errors
  full_run.log                  # last full run log
  India/
    parliamentary_bills/
      Bill9of2026MH.pdf
      ...
  USA_Federal/
    official_gazette/
      2026-15151.pdf
      ...
  UK/
    parliamentary_bills/
      ...
```

## How discovery works

1. HTTP GET the source page (browser-like User-Agent).
2. Parse HTML for `.pdf` anchors / embeds / bare PDF URLs.
3. Follow up to N bill/amendment **detail** pages and pull PDFs there.
4. **Site-specific adapters** when the listing page is JS-heavy or blocked:
   - UK: `bills-api.parliament.uk` publications → PDF links
   - US: Federal Register JSON API → `pdf_url`
   - UK legislation.gov.uk atom feeds
   - EUR-Lex / Canada feeds where available
5. Validate `%PDF` magic bytes before saving.
6. Deduplicate by URL and content hash (resume-safe).

## Why we only had ~254 PDFs before

Coverage audit showed **not** that the sheet only has 254 docs — the collector was incomplete:

| Issue | Effect |
|-------|--------|
| `--max-pdfs-per-source` default **40** | A site with 300+ PDFs stopped at 40 |
| API adapters took one page only (FR `per_page=40`, UK `Take=50`) | Large official inventories truncated |
| No listing pagination | Multi-page gazette indexes barely walked |
| **42 / 67** jurisdictions still at **0 PDFs** | Landing pages 403/404/JS/DNS; need adapters + Playwright |
| ~2200× HTTP **403** on `publications.parliament.uk` | UK bill PDFs discovered via API but blocked on download from datacenter IPs |

Dry-run check after the fix (example): **USA Federal / Federal Register → ~1000 PDF candidates** from one source URL alone.

## Limits / notes

- Some hosts return **403** (e.g. `publications.parliament.uk` from datacenter IPs) even when the API lists the PDF URL. Those stay in `manifest.json` errors for later (browser / proxy / `--playwright`).
- Broken DNS or dead links (e.g. `egazette.nic.in` from some networks) are logged, not fatal.
- Caps: `--max-pdfs-per-source` (default **500**, `0` = unlimited), `--max-follow-pages` (default **80**), `--max-list-pages` (default **15**).
- Polite delay: `--delay` seconds between requests (default 0.5).
- After a deep run, rebuild the app catalog:
  ```bash
  .venv/bin/python collector/index_pdfs_firestore.py   # writes web/data/pdfs_catalog.json
  ```
- Per-source harvest stats are appended to `data/pdfs/manifest.json` → `source_reports` (candidates vs downloaded, errors).

## First goal (this phase)

**Get all amendment and bill PDFs** onto disk under `data/pdfs/`.  
Upload to Firebase Storage / app UI can follow later.

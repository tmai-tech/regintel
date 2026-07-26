# Gazette / Bill PDF collector

Scrapes every URL from the **Gazette & Parliament Bills** sheet (`data/gazette.json`) and downloads **bill / amendment / legislative PDFs** found on those pages (and one level of linked bill pages).

## Script

```bash
# All jurisdictions (resume-safe; skips already-downloaded URLs/hashes)
.venv/bin/python collector/download_gazette_pdfs.py

# One or more jurisdictions
.venv/bin/python collector/download_gazette_pdfs.py \
  --jurisdiction "India" \
  --jurisdiction "USA Federal" \
  --max-pdfs-per-source 25

# Discover only (no files written)
.venv/bin/python collector/download_gazette_pdfs.py --dry-run

# Also crawl legal_databases column
.venv/bin/python collector/download_gazette_pdfs.py --include-legal-db
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

## Limits / notes

- Some hosts return **403** (e.g. `publications.parliament.uk` from datacenter IPs) even when the API lists the PDF URL. Those stay in `manifest.json` errors for later (browser / proxy).
- Broken DNS or dead links (e.g. `egazette.nic.in` from some networks) are logged, not fatal.
- Caps: `--max-pdfs-per-source` (default 40), `--max-follow-pages` (default 12).
- Polite delay: `--delay` seconds between requests (default 0.6).

## First goal (this phase)

**Get all amendment and bill PDFs** onto disk under `data/pdfs/`.  
Upload to Firebase Storage / app UI can follow later.

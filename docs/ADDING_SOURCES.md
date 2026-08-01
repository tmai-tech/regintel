# Adding sources & crawling PDFs

**The crawler is code, not a person.**  
It uses the same strategy as the colleague **`Extraction_Script.py`**: full **BFS same-site crawl** + automatic **Playwright** fallback for JS pages.

```
Your links
   │
   ├─ Excel “Gazette & Parliament Bills”  →  scripts/seed_from_excel.py  →  data/gazette.json
   ├─ data/extra_links.txt  (optional one-off list)
   └─ CLI: --url https://…
            │
            ▼
   collector/download_gazette_pdfs.py
        → collector/site_crawler.py   (BFS + requests + Playwright)
            │
            ▼
   data/pdfs/<jurisdiction>/…  +  manifest.json  +  crawl_log.txt
            │
            ▼
   collector/index_pdfs_firestore.py    →  web/data/pdfs_catalog.json (app UI)
```

## What the code does on each URL (full-site, colleague pattern)

For **any** public page you provide:

1. **BFS crawl** same-site pages (default up to **500** pages per source; raise with `--max-pages 2000`).  
2. Plain HTTP first; if the page is a JS shell / empty / blocked → **Playwright Chromium**.  
3. Collect **every `.pdf`** (and optional office docs) from anchors, embeds, and bare URLs in HTML.  
4. Optional host APIs (Federal Register, UK Bills, …) as extras.  
5. Download PDFs; dedupe by URL + content hash; resume-safe.  
6. Progress saved to `manifest.json` and `crawl_log.txt`.

You do **not** need a new adapter for a normal HTML gazette/bills page.

## 1. Add permanent links (recommended)

1. Open **BCI Tracking Plan.xlsx** → sheet **Gazette & Parliament Bills**.  
2. Add a row (or paste more URLs in existing cells; separate multiple URLs with `;`).  
   - Parliamentary Bills  
   - Official Gazette / Legal Publications  
   - Relevant Legal Databases (optional)  
3. Seed JSON:

```bash
.venv/bin/python scripts/seed_from_excel.py
```

4. Crawl everything (or one jurisdiction):

```bash
# all gazette sources — full site BFS (up to 500 pages each), unlimited PDFs
scripts/crawl_sources.sh --max-pages 500 --max 0

# deep crawl like the colleague script (2000 pages/site)
scripts/crawl_sources.sh --max-pages 2000 --max 0

# only one place
scripts/crawl_sources.sh --jurisdiction "USA Federal" --max-pages 500 --max 0
```

Or without the wrapper:

```bash
.venv/bin/python collector/download_gazette_pdfs.py --max-pages 500 --max-pdfs-per-source 0
.venv/bin/python collector/index_pdfs_firestore.py --skip-firestore
```

## 2. Test a future link before putting it in Excel

Same crawler, one URL:

```bash
# discover only
scripts/crawl_sources.sh --dry-run --url-only \
  --url "https://example.gov/bills" \
  --label "Example Country"

# download for real
scripts/crawl_sources.sh --url-only \
  --url "https://example.gov/bills" \
  --label "Example Country" \
  --max 0
```

Direct CLI:

```bash
.venv/bin/python collector/download_gazette_pdfs.py \
  --url-only \
  --url "https://example.gov/bills" \
  --label "Example Country" \
  --kind parliamentary_bills \
  --max-pdfs-per-source 0
```

If dry-run shows **many PDF candidates**, the code can crawl that site family.  
Then add the URL to Excel and seed so daily/full runs include it forever.

## 3. Batch of trial links (file)

`data/extra_links.txt`:

```text
# comments allowed
https://example.gov/bills
Canada | https://www.parl.ca/legisinfo
India | parliamentary_bills | https://prsindia.org/billtrack
```

```bash
scripts/crawl_sources.sh --from-file data/extra_links.txt --url-only --max 0
```

JSON also works: list of `{"url":"…","jurisdiction":"…","source_kind":"…"}`.

## 4. Full refresh after a big crawl

```bash
scripts/crawl_sources.sh --seed --max 0 --include-legal-db --laws
```

This:

1. Re-reads Excel → `data/gazette.json`  
2. Crawls all sources  
3. Rebuilds `web/data/pdfs_catalog.json` (+ Android assets)  
4. Rebuilds `laws_catalog.json` if `--laws`

## Caps that matter

| Flag | Default | Meaning |
|------|---------|---------|
| `--max-pages` | 500 | BFS HTML pages per source (colleague script: 2000) |
| `--max-pdfs-per-source` / `--max` | 0 | Max **new** PDFs downloaded per source (`0` = unlimited) |
| `--delay` | 0.4 | Seconds between requests (politeness) |
| `--include-legal-db` | off | Also crawl the legal databases column |
| `--no-playwright` | off | Disable JS fallback |

A site with 300+ PDFs needs enough `--max-pages` and unlimited `--max 0`.

## When a new site fails

| Symptom | What to try |
|---------|-------------|
| 0 candidates in dry-run | Page may be JS-only → `--playwright`, or wrong URL |
| Many candidates, many HTTP 403 | Host blocks datacenter IPs; need proxy/browser later |
| 404 on source URL | Fix the link in Excel (example: Singapore bills path) |
| Only ~40 PDFs | Raise `--max` / use `--max 0` |

Check `data/pdfs/manifest.json` → `source_reports` and `errors` after each run.

## CI / product path

- **Web UI** reads `web/data/pdfs_catalog.json` (rebuilt by indexer).  
- **Android** uses the same catalog (assets + optional Firestore).  
- Re-run crawl + index whenever you add links; no manual download by an agent is required.

## Mental model for colleagues

> “Put the official page link in the sheet (or pass `--url`). Run `scripts/crawl_sources.sh`. The **code** opens the site, follows links, and saves PDFs. More links later = same command.”

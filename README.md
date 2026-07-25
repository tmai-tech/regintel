# BCI RegIntel

Regulatory / legal-act intelligence for BCI: catalog of **1,300+ primary sources**, gazette links, secondary sources, tracking log, plus a **scheduled daily collector** and a **web UI** with detailed filterable tables.

## Live UI

After GitHub Pages is enabled, open:

**https://tmai-tech.github.io/regintel/**

Tabs:

| Tab | Content |
|-----|---------|
| Tracking log | Analyst tracking sheet (country, law area, topic, relevancy, links) |
| Primary sources | Full Primary Links catalog |
| Collector updates | Items discovered by the daily Python job |
| Gazette & bills | Parliament / gazette / legal DB URLs |
| Secondary sources | Law firm & commercial watch sources |
| Detailed plan | Workstream coverage & frequency |

## Repo layout

```
regintel/
├── BCI Tracking Plan.xlsx      # source workbook
├── data/                       # JSON catalog + collector output
├── web/                        # GitHub Pages UI
├── collector/run_daily.py      # scheduled fetcher
├── scripts/seed_from_excel.py  # Excel → JSON
├── app/streamlit_app.py        # optional local Streamlit UI
└── .github/workflows/          # daily collector + Pages deploy
```

## Local setup

```bash
# Python 3.12+
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt

# Rebuild JSON from Excel
.venv/bin/python scripts/seed_from_excel.py

# Run collector (pilot: 40 sources)
.venv/bin/python collector/run_daily.py --limit 40 --force

# UI — either open web/index.html via a static server:
.venv/bin/python -m http.server 8080 --directory web
# → http://localhost:8080

# or Streamlit:
.venv/bin/streamlit run app/streamlit_app.py
```

## GitHub Actions

- **Deploy UI to GitHub Pages** — on push to `main` (web/data changes)
- **Daily collector** — cron `0 6 * * *` UTC + manual `workflow_dispatch`

Enable **Settings → Pages → Source: GitHub Actions** once after the first push.

## Notes

- Collector uses polite rate limits and a clear User-Agent.
- Paywalled secondary databases are listed for manual review; logins are not automated.
- First collector pass seeds seen URLs so later runs only report **new** links.

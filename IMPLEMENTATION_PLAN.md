# BCI Regulatory Intelligence — Implementation Plan

## 1. Context & problem

The **BCI Tracking Plan** workbook defines a multi-jurisdiction regulatory monitoring operation: analysts manually check government / regulator / gazette / secondary sites for legal and policy updates relevant to BCI’s Private Markets, Capital Markets, and Enterprise workstreams.

Today that work lives in Excel:

| Sheet | Role | Scale |
|-------|------|-------|
| **Summary Plan** | Workstream ownership, URL counts, tracking cadence | ~1,300+ primary URLs + secondary |
| **Detailed Plan** | Sub-categories, FLR/SLR owners, country coverage | ~40+ topic areas |
| **Primary Links** | Master source registry (region, jurisdiction, authority, URL, segment, topics) | **~1,330 sources / ~70 jurisdictions** |
| **Gazette & Parliament Bills** | Official bills, gazettes, statute databases | **~68 jurisdictions** |
| **Secondary Sources** | Law firms, commercial DBs, news (Mondaq, Lexis, Bloomberg, etc.) | **~68 sources** |
| **Tracking Sheet** | Daily capture log (update, relevancy, assignment, impact) | ~114 sample rows (workflow template) |
| **Sheet8** | Jurisdiction coverage by segment (NA / EU / APAC / ME / LATAM) | Complete coverage lists |

**Pain:** manual daily browsing of hundreds of URLs; no durable store of “what changed”; hard to search past findings; schedule by region/topic is hard to enforce.

**Goal:** automate discovery of *new or changed* legal/regulatory content on a schedule, store it cleanly, and give the team an app to review, filter, fetch detail, and mark relevancy / assignment (replacing the Tracking Sheet workflow).

---

## 2. Product outcomes

### 2.1 Scheduled collector (Python service)

A long-running / cron-driven Python process that:

1. Loads the **source catalog** (imported from Primary Links + Gazette + Secondary).
2. On each source’s schedule (daily / 2–3× week / weekly / monthly — see Summary Plan), **fetches** the page or feed.
3. Detects **new or changed content** (hash, item list, pub date, RSS/Atom if present).
4. Extracts structured fields: title, publication date, URL, snippet/body, jurisdiction, authority, segment, topics.
5. Deduplicates and writes **candidate updates** into a database.
6. Emits run logs, failure alerts, and per-source health (broken URLs, blocks, timeouts).

### 2.2 Review & fetch app

A web app for the team (FLR / SLR / COE) to:

1. **Browse / search** candidate updates (by date, country, segment, topic, relevancy, assignee).
2. **Open / fetch** full content (cached snapshot + live link).
3. **Triage** using Tracking Sheet fields: Relevancy, Remarks, COR Impact, Assigned to, SLR, Alert Status.
4. **Trigger on-demand fetch** for a source or jurisdiction (“check now”).
5. **Admin**: manage sources, schedules, owners (FLR/SLR), import Excel updates.
6. **Exports** to Excel/CSV matching Tracking Sheet columns for handoff.

---

## 3. Domain model (from the sheets)

### 3.1 Workstreams & segments

- **Capital Markets** — ESG, securities, derivatives, market abuse, take-private, etc.
- **Private Markets** — FDI/nat sec, M&A, D&O, funds, crypto, foreign investor rules, etc.
- **Enterprise** — EHS, employment, modern slavery, AML/ABAC, tax, privacy/AI, sanctions, FOI, pensions, etc.

Sources can map to one or more segments (Primary Links column H is multi-valued; normalize on import).

### 3.2 Cadence (Summary Plan)

| Scope | Cadence |
|-------|---------|
| Employment / EHS / Modern Slavery | Daily |
| Corporate governance / entity / disputes | Daily (some 2× week) |
| AML / ABAC / Lobbying | Daily (review 1× / 2 weeks) |
| Sanctions / FOI / IPR / procurement / pensions | Daily (review 1× / 2 weeks) |
| Privacy / cyber / AI | Monthly |
| Direct / indirect tax | Monthly |
| Secondary sources | Every day |
| NA / EU / UK (capital & private) | 2× week (EU members weekly) |
| APAC | 3× week |
| MEA / LATAM | 2× week |

**Implementation:** each source gets a `schedule_class` and `next_run_at`. The scheduler only visits sources due that day, so daily jobs stay bounded.

### 3.3 Tracking record (target schema ≈ Tracking Sheet)

| Field | Purpose |
|-------|---------|
| country / federal_or_state | Jurisdiction |
| period_of_tracking / date_of_tracking | When we ran |
| date_of_publication | Source pub date |
| law_area | Capital / Private / Enterprise |
| topical_relevance | Sub-category (from Detailed Plan / Primary Links topics) |
| link_for_update | Canonical URL of the item |
| remarks | Title / summary |
| tracked_by | FLR user |
| relevancy | Relevant / Not Relevant |
| comments | Analyst notes |
| cor_impact | Yes / No |
| assigned_to / slr_name | Workflow |
| alert_status | Pipeline state |
| last_tracked | Last successful source visit |
| kmp_id | Optional external ID |
| source_id | FK to catalog |
| content_hash / snapshot_path | Dedup & audit |

### 3.4 Source catalog (from Primary Links)

Normalize columns A–U into:

- `region`, `jurisdiction`, `authority_name`, `authority_type`
- `link_nature` (News, Laws & Regulations, Consultations, …) — **normalize synonyms**
- `url`, `update_frequency_hint` (Frequent / Less Frequent / …)
- `segments[]`, `topics[]`
- `source_kind`: `primary` | `gazette_bills` | `gazette_official` | `legal_db` | `secondary`
- `status`: active | broken | login_required | skip
- `scrape_strategy`: `http_html` | `rss` | `sitemap` | `playwright` | `manual_only`
- `owner_flr`, `owner_slr` (join from Detailed / Summary Plan)

---

## 4. Recommended architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        regintel monorepo                         │
├──────────────────────────┬──────────────────────────────────────┤
│  collector/ (Python)     │  app/ (web UI + API)                 │
│  - scheduler             │  - FastAPI (or Django) backend       │
│  - fetchers              │  - React/Next or simple HTMX UI      │
│  - extractors            │  - auth (SSO/basic)                  │
│  - change detection      │  - review queue & search             │
│  - seed importers        │  - on-demand re-fetch API            │
└────────────┬─────────────┴──────────────┬───────────────────────┘
             │                            │
             ▼                            ▼
        ┌────────────────────────────────────────┐
        │  PostgreSQL  (+ optional Redis queue)  │
        │  object store / disk for HTML snapshots│
        └────────────────────────────────────────┘
```

### Why this split

| Piece | Why |
|-------|-----|
| **Python collector** | Scraping, scheduling, Playwright, PDF, language tooling fit Python; matches “continuous daily script”. |
| **App** | Team needs filters, assignment, fetch-on-demand — not only log files. |
| **PostgreSQL** | Structured search (jurisdiction, segment, date), multi-user workflow, audit. |
| **Redis/RQ or Celery (optional Phase 2)** | Parallel fetch of 1k+ URLs without one giant process. |

### Runtime modes for the collector

1. **Cron / systemd timer (recommended start):** `python -m collector run --due-today` once or several times per day.
2. **Long-running scheduler:** APScheduler / asyncio loop inside a container for “always on”.
3. **On-demand:** API enqueues `fetch_source(source_id)` for the app’s “Check now”.

Start with (1) + (3); add (2) only if you need sub-hour frequency.

---

## 5. Collection pipeline (detail)

### Phase A — Seed & normalize

1. Import `BCI Tracking Plan.xlsx`:
   - Primary Links → `sources`
   - Gazette sheet → 2–3 source rows per jurisdiction (bills / gazette / legal DB)
   - Secondary Sources → `sources` with `source_kind=secondary`, `scrape_strategy=manual_only` or RSS where available
   - Detailed Plan → topics + owner map
   - Tracking Sheet → optional historical `updates` seed
2. URL cleanup (add scheme, strip tracking params, flag “Website not working”).
3. Normalize enums: region, segment, link_nature, frequency.
4. Assign default schedule from region + segment + Summary Plan rules.

### Phase B — Fetch strategies (priority order)

| Priority | Strategy | When |
|----------|----------|------|
| 1 | **RSS/Atom / JSON API** | Prefer if discoverable (many “News” pages have feeds) |
| 2 | **HTTP GET + HTML parse** | Static news/list pages (majority of Primary Links) |
| 3 | **Conditional requests** | `ETag` / `Last-Modified` / body hash to skip work |
| 4 | **Playwright** | JS-rendered or anti-bot sites only |
| 5 | **Sitemap / listing crawl (depth 1)** | Laws & regulations index pages |
| 6 | **Manual / login** | Lexis, Bloomberg, vLex, DataGuidance, etc. — **do not automate logins** without legal/compliance approval; surface as “check checklist” in app |

**Respect:** robots.txt where applicable, rate limits (e.g. 1 req/s per domain), User-Agent identifying the service, retries with backoff.

### Phase C — Change detection

For each source run:

1. Fetch listing page or feed.
2. Extract **items** (title, url, date if present).
3. Compare item URLs (and optional content hash) to `seen_items`.
4. New items → create `update_candidates` with status `new`.
5. If listing has no stable items (homepage only): hash main content block; on change, create a single “page changed” candidate with snapshot for human review.

### Phase D — Enrichment (optional, Phase 2)

- Language detect + translate title/snippet (many EU/LATAM/APAC pages).
- Keyword / embedding relevance score vs BCI topic taxonomy (assist, not auto-close).
- PDF download + text extract for gazette PDFs.

### Phase E — Human workflow (app)

```
new → under_review → relevant | not_relevant
relevant → assigned → alerted / closed
```

Maps to Tracking Sheet: Relevancy, Assigned to, SLR Name, Alert Status, COR Impact.

---

## 6. App features (MVP → later)

### MVP (must have)

- Dashboard: today’s new candidates; failed sources; sources due / overdue.
- List + filters: date range, region, jurisdiction, segment, topic, relevancy, assignee.
- Detail pane: title, summary, pub date, source authority, open link, cached HTML/text.
- Actions: mark Relevant / Not Relevant, comment, assign, COR Impact, export selection to Tracking Sheet CSV.
- Source browser: search Primary Links catalog; last success; next run; “Fetch now”.
- Auth: simple user accounts or SSO stub (team size is small).

### Phase 2

- Saved views per FLR (e.g. Alisha = Capital/Private NA-EU).
- Email/Teams digest of “Relevant” items for SLR.
- Coverage heatmap (Sheet8-style: jurisdictions × segment).
- Analytics: volume by country/topic, time-to-triage.
- Secondary-source watchlists (RSS where free).

### Out of scope for v1

- Full legal research DB / opinion writing.
- Guaranteed 100% coverage of paywalled commercial tools.
- Auto-filing regulatory obligations.

---

## 7. Tech stack (proposed)

| Layer | Choice | Notes |
|-------|--------|-------|
| Language | Python 3.12+ | Collector + API |
| HTTP | `httpx` + `tenacity` | Async-capable fetches |
| HTML | `selectolax` or BeautifulSoup | Fast listing parse |
| Browser | Playwright (optional extra) | Hard sites only |
| Scheduler | APScheduler or system cron | Cron is simpler for v1 |
| DB | PostgreSQL 16 | JSONB for flexible topics |
| ORM / migrations | SQLAlchemy 2 + Alembic | |
| API | FastAPI | Serves app + on-demand fetch |
| UI | Next.js **or** FastAPI + HTMX/Jinja | HTMX faster for internal tool; Next if you want rich SPA |
| Packaging | `uv` / poetry, Docker Compose | DB + app + collector |
| Config | `.env` + YAML source overrides | Per-domain rate limits, selectors |
| Observability | structured logs (JSON), simple metrics table | |

---

## 8. Repository layout (suggested)

```
regintel/
├── BCI Tracking Plan.xlsx          # source of truth for seed
├── IMPLEMENTATION_PLAN.md
├── README.md
├── docker-compose.yml
├── .env.example
├── data/                           # snapshots, exports (gitignored)
├── packages/ or src/
│   ├── collector/
│   │   ├── __main__.py             # CLI: seed, run, fetch-one
│   │   ├── scheduler.py
│   │   ├── fetchers/
│   │   ├── extractors/
│   │   ├── change_detect.py
│   │   └── importers/excel_seed.py
│   ├── app/
│   │   ├── api/
│   │   ├── ui/ or frontend/
│   │   └── services/
│   └── shared/
│       ├── models.py
│       ├── db.py
│       └── taxonomy.py             # segments, topics, regions
├── tests/
└── scripts/
    ├── seed_from_excel.py
    └── export_tracking_sheet.py
```

---

## 9. Delivery phases

### Phase 0 — Foundations (3–5 days)

- [ ] Repo, Docker Compose (Postgres), env, lint/test harness
- [ ] SQLAlchemy models: Source, FetchRun, UpdateCandidate, User, Assignment
- [ ] Excel importer for Primary Links + Gazette + Secondary (+ optional Tracking seed)
- [ ] CLI: `seed`, `list-sources`, `stats`
- [ ] Enum normalization + URL validation report (broken / missing scheme)

**Exit:** catalog loaded; can query “how many active sources by region”.

### Phase 1 — Collector MVP (1–2 weeks)

- [ ] HTTP fetcher with rate limit, robots-aware optional, hashing
- [ ] Generic list-page extractor (links + dates via heuristics)
- [ ] RSS discovery (`/feed`, `<link rel="alternate">`)
- [ ] Change detection → insert candidates
- [ ] Cron entry: daily full of “due” sources; optional mid-day secondary pass
- [ ] Snapshot storage under `data/snapshots/{source_id}/{run_id}.html`
- [ ] Failure recording + retry policy
- [ ] Unit tests with fixture HTML; integration test against a few stable gov sites

**Exit:** overnight run produces new candidates for a pilot set (e.g. Canada Federal + UK + US Federal, ~150 sources).

### Phase 2 — App MVP (1–2 weeks, can overlap late Phase 1)

- [ ] Auth (basic users: FLR names from plan)
- [ ] Review queue UI + filters
- [ ] Detail + mark relevancy / assign / comments
- [ ] Export Tracking Sheet-compatible CSV
- [ ] “Fetch now” button → collector job
- [ ] Dashboard: new today, failures, overdue

**Exit:** analysts can replace manual Tracking Sheet entry for pilot jurisdictions.

### Phase 3 — Scale & harden (2–3 weeks)

- [ ] Expand pilot → all Primary Links (~1,330)
- [ ] Playwright path for JS-heavy sources
- [ ] Per-domain config (CSS selectors where heuristics fail)
- [ ] Schedule matrix fully aligned to Summary Plan (region × segment)
- [ ] Secondary sources: free RSS/public pages only; rest as manual checklist
- [ ] Gazette PDF handling for high-priority jurisdictions
- [ ] Alert digest email/Teams
- [ ] Health report: % sources succeeding 7d

**Exit:** production daily job for full catalog; app is system of record for triage.

### Phase 4 — Intelligence (optional)

- [ ] Topic auto-tag from keywords / embeddings
- [ ] Translation for non-English titles
- [ ] Coverage vs Sheet8 matrix in UI
- [ ] Historical trend reports

---

## 10. Pilot recommendation

Do **not** scrape all 1,330 URLs on day one. Pilot:

| Batch | Why |
|-------|-----|
| **Canada Federal + BC** (~126 primary links) | Core BCI footprint; English; stable gov sites |
| **UK + EU institutions** | High Capital/Private volume |
| **US Federal + NY** | Dense regulator set |
| **Gazette set for same jurisdictions** | Bills/official publications |

Success criteria for pilot:

1. ≥ 80% sources return HTTP success over 7 days.
2. False-new rate manageable (dedup works).
3. Analysts confirm candidates match what they would have logged manually.
4. End-to-end: discover → triage → export.

---

## 11. Scheduling design

```
Daily 06:00 local  → collector run --schedule daily|frequent
Mon/Wed/Fri 07:00  → collector run --region APAC
Tue/Thu 07:00      → collector run --region MEA,LATAM
Mon/Thu 07:00      → collector run --region NA,EU,UK
1st of month 08:00 → collector run --schedule monthly   # tax, privacy, etc.
Every day 09:00    → collector run --kind secondary --public-only
```

Inside each run: process only sources with `next_run_at <= now` and `status=active`. Update `last_success_at` / `next_run_at` after each source.

---

## 12. Data model (sketch)

```text
sources
  id, region, jurisdiction, authority_name, authority_type,
  url, link_nature, source_kind, segments[], topics[],
  schedule_class, next_run_at, last_success_at, last_error,
  scrape_strategy, config jsonb, status, owners...

fetch_runs
  id, source_id, started_at, finished_at, http_status,
  bytes, content_hash, item_count, error, snapshot_path

update_candidates
  id, source_id, fetch_run_id, title, item_url, published_at,
  snippet, law_area, topics[], content_hash,
  status, relevancy, comments, cor_impact,
  tracked_by, assigned_to, slr_name, alert_status,
  created_at, reviewed_at

seen_items
  source_id, item_url_hash, first_seen_at, last_seen_at

users
  id, name, role (flr|slr|admin), email
```

---

## 13. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Site structure diversity (1k+ unique layouts) | Generic heuristics first; selector overrides only for high-value failures |
| JS / bot protection | Playwright pool; lower frequency; official APIs/RSS first |
| Paywalled secondary (Lexis, Bloomberg, vLex) | Catalog as manual; do not store credentials in v1 |
| Legal / ToS of scraping | Prefer public gov sources; rate limit; document purpose; legal review for commercial sites |
| Non-English content | Store original; optional translate in Phase 4 |
| Excel drift (catalog updates) | Re-import tool with upsert by URL; don’t hand-edit prod DB only |
| Noise (irrelevant news) | Human relevancy gate remains; optional ML assist later |
| Date parsing mess (Excel serials in Tracking Sheet) | Robust date parser; store UTC timestamps |

---

## 14. Compliance & ethics

- Primary focus: **public government and regulator websites** and official gazettes.
- Identify User-Agent: `BCI-RegIntel/1.0 (+contact-email)`.
- No circumvention of paywalls or CAPTCHAs.
- Store snapshots for audit of “what we saw when,” with retention policy (e.g. 90 days).
- Access control on the app (internal only).

---

## 15. Success metrics

| Metric | Target (after Phase 3) |
|--------|------------------------|
| Active primary sources polled on schedule | ≥ 95% of non-broken catalog |
| Fetch success rate (7-day) | ≥ 85% |
| Time from publish → candidate in DB | ≤ 24–48h for daily sources |
| Analyst triage time vs pure manual browse | Clear reduction (qualitative + hours/week) |
| Tracking Sheet export used without retyping | Yes |

---

## 16. Immediate next steps (when implementation starts)

1. Confirm stack preferences (HTMX internal app vs React; host: local Docker vs cloud).
2. Confirm pilot jurisdictions and timezone for cron.
3. Confirm auth (shared password vs individual users vs SSO).
4. Scaffold monorepo + Postgres + Excel seed importer.
5. Implement collector for pilot sources + minimal review API/UI.
6. Run 1 week shadow mode (collect only; analysts still use Excel) then cut over triage to app.

---

## 17. Summary

The BCI Tracking Plan is already a complete **operating model**: source registry, topic taxonomy, ownership, cadence, and triage fields. The software should not invent a new process — it should **automate discovery and house the Tracking Sheet workflow**.

| Component | Role |
|-----------|------|
| **Python scheduled collector** | Visit due sources daily/weekly/monthly; detect new legal/regulatory items; snapshot & store |
| **App** | Search, fetch detail, triage relevancy/assignment, export, manage sources |

Build in a **pilot → scale** path so value appears in weeks, not after boiling the ocean of 1,330 heterogeneous websites.

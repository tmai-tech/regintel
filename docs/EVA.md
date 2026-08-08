# Eva — PDF research agent

**Eva** is your **PDF research assistant** (ChatGPT-with-browsing style, but **only our PDF library** — not the open web).

She **searches indexed SDAIA/RegIntel PDFs**, pulls relevant summaries and passages, and answers with **citations + PDF links**.

## Architecture

```
User question (Eva chat)
        │
        ▼
Retrieve top PDFs from eva_summaries (keyword / bilingual score)
        │
        ├── optional deep read: extract passages from PDF text
        ▼
Synthesize answer + citations (client RAG, or SpaceXAI via eva_server)
        │
        ▼
Show answer + clickable PDF references

Offline batch index:
PDF catalog / local files / remote open_url
        │
        ▼
collector/eva_extract.py     → plain text
collector/eva_summarize.py   → summary JSON (XAI_API_KEY → LLM, else extractive)
        ├── data/eva/summaries.jsonl
        └── web/data/eva_summaries.json
```

## Setup

```bash
.venv/bin/pip install -r requirements.txt
export XAI_API_KEY=...          # https://console.x.ai  (recommended)
# optional model override
export XAI_MODEL=grok-4.5
```

Without `XAI_API_KEY`, Eva still indexes PDFs using **extractive** summaries (no cloud LLM).

## Build Eva’s knowledge (batch)

```bash
# summarize next N missing PDFs (prefers Saudi when filtered)
.venv/bin/python collector/eva_summarize.py --limit 50 --jurisdiction "Saudi"
.venv/bin/python collector/eva_summarize.py --limit 100

# rebuild site JSON only
.venv/bin/python collector/eva_summarize.py --publish-only
```

GitHub Actions workflow **Eva summarize PDFs** runs on a schedule (needs repo secret `XAI_API_KEY` for LLM quality).

## Ask Eva (CLI)

```bash
.venv/bin/python collector/eva_agent.py "What does the NCA guidance say about cyber?"
.venv/bin/python collector/eva_agent.py --interactive
```

Answers include **References** with title + URL for each cited PDF.

## Optional LLM API for the website

Static GitHub Pages cannot hold your API key. For full LLM answers in the **Eva** tab:

```bash
export XAI_API_KEY=...
.venv/bin/python tools/eva_server.py --port 8787
```

In the browser console (or set before load):

```js
localStorage.setItem("regintel_eva_api", "http://127.0.0.1:8787");
```

Without the API, the site still answers via **retrieval over published summaries** and always shows PDF links.

## Naming

- Agent: **Eva**
- Site tab: **Eva**
- Env: `XAI_API_KEY` (SpaceXAI / xAI)

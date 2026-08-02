"""SpaceXAI / xAI client helpers for Eva (OpenAI-compatible API)."""
from __future__ import annotations

import json
import os
import re
from typing import Any


def get_client():
    """Return OpenAI-compatible client for api.x.ai or None if no key."""
    key = os.environ.get("XAI_API_KEY") or os.environ.get("xai_api_key")
    if not key:
        return None
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai package required: pip install openai") from e
    return OpenAI(api_key=key, base_url="https://api.x.ai/v1")


def model_name() -> str:
    return os.environ.get("XAI_MODEL", "grok-4.5")


def chat_text(system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 1200) -> str:
    client = get_client()
    if client is None:
        raise RuntimeError("XAI_API_KEY not set")
    # Prefer chat.completions (widely available); fall back to responses if needed
    try:
        resp = client.chat.completions.create(
            model=model_name(),
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        resp = client.responses.create(
            model=model_name(),
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = getattr(resp, "output_text", None)
        if text:
            return str(text).strip()
        return json.dumps(resp.model_dump() if hasattr(resp, "model_dump") else {})[:4000]


def summarize_pdf_text(
    *,
    title: str,
    jurisdiction: str,
    url: str,
    text: str,
) -> dict[str, Any]:
    """Return structured summary dict using LLM, or extractive fallback."""
    client = get_client()
    snippet = text[:35_000]
    if not snippet.strip():
        return {
            "summary": "No extractable text (may be scanned/image-only PDF).",
            "key_points": [],
            "topics": [],
            "document_type": "unknown",
            "method": "empty",
        }

    if client is None:
        return extractive_summary(title=title, text=snippet)

    system = (
        "You are Eva, a regulatory research analyst for BCI RegIntel. "
        "Summarize legal/regulatory PDFs accurately. "
        "Reply with ONLY valid JSON (no markdown fences) with keys: "
        "summary (string, 3-6 sentences), "
        "key_points (array of 3-8 short strings), "
        "topics (array of 2-6 short topic tags), "
        "document_type (one of: bill, amendment, regulation, gazette, report, guidance, notice, other)."
    )
    user = (
        f"Title: {title}\n"
        f"Jurisdiction: {jurisdiction}\n"
        f"Source URL: {url}\n\n"
        f"Document text (may be truncated):\n{snippet}"
    )
    raw = chat_text(system, user, temperature=0.15, max_tokens=900)
    data = _parse_json_object(raw)
    if not data:
        return extractive_summary(title=title, text=snippet) | {"method": "llm_parse_fallback", "raw": raw[:500]}
    return {
        "summary": str(data.get("summary") or "").strip() or extractive_summary(title=title, text=snippet)["summary"],
        "key_points": [str(x).strip() for x in (data.get("key_points") or []) if str(x).strip()][:10],
        "topics": [str(x).strip() for x in (data.get("topics") or []) if str(x).strip()][:8],
        "document_type": str(data.get("document_type") or "other").strip().lower(),
        "method": "llm",
    }


def answer_with_context(
    *,
    question: str,
    contexts: list[dict],
) -> dict[str, Any]:
    """Answer a question using retrieved PDF summaries; always cite sources."""
    if not contexts:
        return {
            "answer": "I could not find relevant PDF summaries for that question yet. "
            "Run Eva summarization on more PDFs, then try again.",
            "citations": [],
            "method": "none",
        }

    # Build citation blocks
    blocks = []
    citations = []
    for i, c in enumerate(contexts, 1):
        citations.append(
            {
                "n": i,
                "id": c.get("id"),
                "title": c.get("title"),
                "jurisdiction": c.get("jurisdiction"),
                "url": c.get("url") or c.get("open_url"),
                "source_page": c.get("source_page"),
            }
        )
        blocks.append(
            f"[{i}] Title: {c.get('title')}\n"
            f"Jurisdiction: {c.get('jurisdiction')}\n"
            f"URL: {c.get('url') or c.get('open_url')}\n"
            f"Summary: {c.get('summary')}\n"
            f"Key points: {'; '.join(c.get('key_points') or [])}"
        )

    client = get_client()
    if client is None:
        # Offline synthesis
        lines = [
            f"Based on {len(contexts)} PDF summary(ies) in Eva's index:\n",
        ]
        for c in contexts[:5]:
            lines.append(f"• {c.get('title')}: {(c.get('summary') or '')[:280]}")
        lines.append("\nReferences:")
        for cit in citations:
            lines.append(f"[{cit['n']}] {cit.get('title')} — {cit.get('url')}")
        return {"answer": "\n".join(lines), "citations": citations, "method": "retrieve_only"}

    system = (
        "You are Eva, RegIntel's regulatory research assistant. "
        "Answer ONLY from the provided PDF summaries. "
        "If the answer is not in the sources, say you don't know from the indexed PDFs. "
        "Cite sources inline like [1], [2]. "
        "End with a short 'References' list mapping [n] to document title and URL."
    )
    user = f"Question: {question}\n\nSources:\n\n" + "\n\n---\n\n".join(blocks)
    answer = chat_text(system, user, temperature=0.2, max_tokens=1400)
    return {"answer": answer, "citations": citations, "method": "llm"}


def extractive_summary(*, title: str, text: str) -> dict[str, Any]:
    """Heuristic summary when no LLM key is available."""
    # Split into sentences-ish
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    sents = [c.strip() for c in chunks if 40 <= len(c.strip()) <= 400]
    # Prefer sentences with legal keywords
    keywords = (
        "shall", "regulation", "amend", "act", "bill", "article", "section",
        "authority", "ministry", "license", "compliance", "tax", "bank",
        "cyber", "data", "privacy", "insurance", "securities", "competition",
    )
    scored = []
    for s in sents:
        score = sum(1 for k in keywords if k in s.lower())
        scored.append((score, s))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    top = [s for _, s in scored[:5]] or sents[:3] or [text[:500]]
    summary = " ".join(top)[:1200]
    if title:
        summary = f"{title}. " + summary
    # crude topics from frequent words
    words = re.findall(r"[A-Za-z]{5,}", text.lower())
    stop = {"which", "their", "there", "these", "those", "about", "shall", "under", "would", "could", "between"}
    freq: dict[str, int] = {}
    for w in words:
        if w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    topics = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:6]]
    return {
        "summary": summary.strip(),
        "key_points": top[:5],
        "topics": topics,
        "document_type": "other",
        "method": "extractive",
    }


def _parse_json_object(raw: str) -> dict | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    # strip fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

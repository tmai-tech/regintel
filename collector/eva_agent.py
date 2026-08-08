#!/usr/bin/env python3
"""
Eva agent: answer questions over summarized PDFs with citations.

Usage:
  .venv/bin/python collector/eva_agent.py "What cyber rules are in the catalog?"
  .venv/bin/python collector/eva_agent.py --interactive
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from eva_llm import answer_with_context, get_client  # type: ignore

WEB_SUMMARIES = ROOT / "web" / "data" / "eva_summaries.json"
JSONL = ROOT / "data" / "eva" / "summaries.jsonl"


def load_summaries() -> list[dict]:
    rows: list[dict] = []
    if WEB_SUMMARIES.exists():
        data = json.loads(WEB_SUMMARIES.read_text(encoding="utf-8"))
        if isinstance(data, list):
            rows = data
    if not rows and JSONL.exists():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    # drop pure errors without content
    return [r for r in rows if (r.get("summary") or "").strip()]


STOP = {
    "the", "and", "for", "are", "you", "your", "what", "when", "where", "which",
    "who", "how", "does", "did", "with", "from", "that", "this", "have", "has",
    "was", "were", "will", "can", "could", "would", "should", "about", "into",
    "more", "any", "all", "our", "its", "not", "but", "also", "than", "then",
    "them", "they", "there", "these", "those", "please", "tell", "give", "show",
    "read", "reading", "pdf", "pdfs", "document", "documents", "file", "files",
}


# tokenize() redefined below with Arabic support (used by retrieve)


def is_meta_question(q: str) -> bool:
    s = (q or "").lower().strip().replace("’", "'")
    if not s:
        return False
    if re.match(r"^(status|progress|update|hello|hi|hey|thanks|thank you)[\s?!.,]*$", s):
        return True
    process = (
        r"(read|reading|extract|extracting|index|indexing|process|processing|"
        r"summariz(?:e|ing)?|crawl(?:ing)?|download(?:ing)?|fetch(?:ing)?)"
    )
    if re.search(rf"\b(will|are|do|can|could|would)\s+you\b", s) and re.search(process, s):
        return True
    if (
        re.search(process, s)
        and re.search(r"\b(more|additional|new|further)\b", s)
        and re.search(r"\b(pdfs?|documents?|files?|summaries|data)\b", s)
    ):
        return True
    if re.search(r"\b(more|additional)\s+(pdfs?|documents?|files?)\b", s):
        return True
    if re.search(r"\bhow many\b", s) and re.search(r"\b(pdfs?|summaries|documents?)\b", s):
        return True
    if re.search(r"\b(are you|do you)\b", s) and re.search(process, s):
        return True
    if re.search(r"\bhave you (read|finished|done|indexed|extracted)\b", s):
        return True
    if (
        re.search(r"\b(list|show|display|name)\b", s)
        and re.search(r"\b(pdfs?|summaries|documents?|files?|them|those|index)\b", s)
    ):
        return True
    if re.search(r"\bgive me (a |the )?list\b", s):
        return True
    patterns = [
        r"\b(still )?(working|running|crawling|indexing|extracting)\b",
        r"\b(progress|update me|status|coverage)\b",
        r"\b(who are you|what (can|do) you do|what is eva)\b",
        r"\bknowledge base\b",
        r"\b(keep|continue)\s+(reading|extracting|indexing)\b",
    ]
    return any(re.search(p, s) for p in patterns)


def meta_answer(question: str, corpus: list[dict]) -> dict:
    n = len(corpus)
    s = (question or "").lower()
    if re.search(r"who are you|what (can|do) you do|hello|hi\b|hey\b", s):
        ans = (
            "I’m Eva, RegIntel’s legal research assistant. "
            f"I have {n} PDF summaries indexed. Ask about a topic or jurisdiction; "
            "I’ll cite source PDFs. Ask “status” or “list the PDFs” for progress / inventory."
        )
        return {
            "answer": ans,
            "citations": [],
            "method": "meta",
            "retrieved": 0,
            "corpus_size": n,
            "llm": get_client() is not None,
        }

    # list indexed PDFs
    if (
        re.search(r"\b(list|show|display|name)\b", s)
        and re.search(r"\b(pdfs?|summaries|documents?|files?|them|those|index)\b", s)
    ) or re.search(r"\bgive me (a |the )?list\b", s):
        lines = [f"Here are the {n} PDF(s) I’ve summarized so far:", ""]
        citations = []
        for i, doc in enumerate(corpus, 1):
            url = doc.get("open_url") or doc.get("url") or ""
            title = doc.get("title") or "Untitled"
            jur = doc.get("jurisdiction") or "—"
            citations.append(
                {
                    "n": i,
                    "id": doc.get("id"),
                    "title": title,
                    "jurisdiction": jur,
                    "url": url,
                    "source_page": doc.get("source_page"),
                }
            )
            lines.append(f"[{i}] {title} ({jur})")
            if url:
                lines.append(f"    {url}")
        return {
            "answer": "\n".join(lines),
            "citations": citations,
            "method": "meta_list",
            "retrieved": n,
            "corpus_size": n,
            "llm": get_client() is not None,
        }

    ans = (
        f"Yes — summarization runs in batches in the background.\n"
        f"• Summaries ready: {n}\n"
        f"• LLM mode: {'on' if get_client() else 'off (extractive / set XAI_API_KEY)'}\n\n"
        "Ask “list the PDFs” to see every document I’ve summarized. "
        "I only answer content questions from those summaries."
    )
    return {
        "answer": ans,
        "citations": [],
        "method": "meta",
        "retrieved": 0,
        "corpus_size": n,
        "llm": get_client() is not None,
    }


def tokenize(s: str) -> set[str]:
    """Latin + Arabic tokens for bilingual SDAIA corpus."""
    raw = (s or "").lower()
    lat = set(re.findall(r"[a-z0-9]{3,}", raw))
    ar = set(re.findall(r"[\u0600-\u06ff]{2,}", raw))
    return {t for t in (lat | ar) if t not in STOP}


def retrieve(question: str, corpus: list[dict], *, k: int = 8) -> list[dict]:
    q = tokenize(question)
    q_raw = (question or "").lower().strip()
    if not q and len(q_raw) < 2:
        return []
    scored = []
    for doc in corpus:
        title = str(doc.get("title") or "")
        summary = str(doc.get("summary") or "")
        blob = " ".join(
            [
                title,
                str(doc.get("jurisdiction") or ""),
                summary,
                " ".join(doc.get("key_points") or []),
                " ".join(doc.get("topics") or []),
            ]
        )
        dt = tokenize(blob)
        if not dt and not title:
            continue
        score = len(q & dt) if q else 0
        score += 4 * len(q & tokenize(title))
        j = str(doc.get("jurisdiction") or "").lower()
        title_l = title.lower()
        summary_l = summary.lower()
        for t in q:
            if t in j:
                score += 2
            if len(t) >= 4 and t in title_l:
                score += 2
            if len(t) >= 4 and t in summary_l:
                score += 1
        if len(q_raw) >= 6 and q_raw[:40] in title_l:
            score += 6
        if score >= 1:
            scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return []
    best = scored[0][0]
    min_keep = max(1, best * 0.35) if best >= 6 else 1
    return [d for sc, d in scored if sc >= min_keep][:k]


def _local_pdf_path(doc: dict) -> Path | None:
    """Resolve a local PDF path from catalog-ish fields if present on disk."""
    for key in ("local_path", "path", "filename"):
        p = doc.get(key)
        if not p:
            continue
        path = Path(p)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file() and path.suffix.lower() == ".pdf":
            return path
        # ministry download layout
        cand = ROOT / "data" / "pdfs" / path.name
        if cand.is_file():
            return cand
    return None


def enrich_with_pdf_passages(question: str, hits: list[dict], *, max_docs: int = 3) -> list[dict]:
    """Optional deep read: extract passages from local PDF files for top hits."""
    try:
        from eva_extract import extract_text  # type: ignore
    except Exception:
        return hits

    q = tokenize(question)
    out: list[dict] = []
    for i, doc in enumerate(hits):
        d = dict(doc)
        d["passages"] = list(doc.get("passages") or [])
        if i < max_docs:
            path = _local_pdf_path(doc)
            if path is not None:
                try:
                    text = extract_text(path) or ""
                except Exception:
                    text = ""
                if len(text) > 80:
                    # sliding windows
                    step = 500
                    scored = []
                    for j in range(0, min(len(text), 80_000), step):
                        window = text[j : j + 650].strip()
                        if len(window) < 50:
                            continue
                        dt = tokenize(window)
                        score = len(q & dt)
                        if score >= 1:
                            scored.append((score, window[:700]))
                    scored.sort(key=lambda x: -x[0])
                    d["passages"] = [
                        {"text": w, "score": sc} for sc, w in scored[:3]
                    ]
        out.append(d)
    return out


def ask(question: str, *, k: int = 8, deep: bool = True) -> dict:
    """
    ChatGPT-style Q&A over our PDF library only:
      search summaries → optional deep PDF passages → LLM/extractive answer + citations.
    """
    corpus = load_summaries()
    # Prefer SDAIA when present (site focus)
    sdaia = [
        r
        for r in corpus
        if "sdaia" in str(r.get("jurisdiction") or "").lower()
        or "sdaia" in str(r.get("url") or r.get("open_url") or "").lower()
    ]
    if sdaia:
        corpus = sdaia
    if is_meta_question(question):
        return meta_answer(question, corpus)
    hits = retrieve(question, corpus, k=k)
    if deep and hits:
        hits = enrich_with_pdf_passages(question, hits, max_docs=3)
    result = answer_with_context(question=question, contexts=hits)
    result["retrieved"] = len(hits)
    result["corpus_size"] = len(corpus)
    result["llm"] = get_client() is not None
    result["mode"] = "pdf_rag"
    return result


def main():
    p = argparse.ArgumentParser(description="Eva Q&A over PDF summaries")
    p.add_argument("question", nargs="?", help="Question to ask Eva")
    p.add_argument("--interactive", "-i", action="store_true")
    p.add_argument("--k", type=int, default=8, help="Top summaries to retrieve")
    args = p.parse_args()

    if args.interactive or not args.question:
        print("Eva ready. Corpus:", len(load_summaries()), "summaries.")
        print("LLM:", "on" if get_client() else "off (retrieve-only / set XAI_API_KEY)")
        print("Type a question (or 'quit').\n")
        while True:
            try:
                q = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q or q.lower() in ("quit", "exit", "q"):
                break
            res = ask(q, k=args.k)
            print("\nEva>\n" + res.get("answer") + "\n")
            if res.get("citations"):
                print("Citations:")
                for c in res["citations"]:
                    print(f"  [{c['n']}] {c.get('title')} — {c.get('url')}")
            print()
        return

    res = ask(args.question, k=args.k)
    print(res.get("answer"))
    print("\n---")
    print(json.dumps({"citations": res.get("citations"), "method": res.get("method"), "retrieved": res.get("retrieved"), "corpus_size": res.get("corpus_size")}, indent=2))


if __name__ == "__main__":
    main()

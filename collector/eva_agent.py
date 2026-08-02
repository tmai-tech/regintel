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


def tokenize(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if t}


def retrieve(question: str, corpus: list[dict], *, k: int = 8) -> list[dict]:
    q = tokenize(question)
    if not q:
        return corpus[:k]
    scored = []
    for doc in corpus:
        blob = " ".join(
            [
                str(doc.get("title") or ""),
                str(doc.get("jurisdiction") or ""),
                str(doc.get("summary") or ""),
                " ".join(doc.get("key_points") or []),
                " ".join(doc.get("topics") or []),
            ]
        )
        dt = tokenize(blob)
        if not dt:
            continue
        overlap = len(q & dt)
        # light boost for title hits
        title_t = tokenize(str(doc.get("title") or ""))
        overlap += 2 * len(q & title_t)
        if overlap:
            scored.append((overlap, doc))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:k]]


def ask(question: str, *, k: int = 8) -> dict:
    corpus = load_summaries()
    hits = retrieve(question, corpus, k=k)
    result = answer_with_context(question=question, contexts=hits)
    result["retrieved"] = len(hits)
    result["corpus_size"] = len(corpus)
    result["llm"] = get_client() is not None
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

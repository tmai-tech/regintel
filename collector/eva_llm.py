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
    try:
        from eva_extract import clean_extracted_text
    except ImportError:
        from collector.eva_extract import clean_extracted_text  # type: ignore

    client = get_client()
    snippet = clean_extracted_text(text)[:35_000]
    if not snippet.strip():
        return {
            "summary": "No extractable text (may be scanned/image-only PDF).",
            "key_points": [],
            "topics": [],
            "document_type": "unknown",
            "method": "empty",
        }

    if client is None:
        return extractive_summary(
            title=title, text=snippet, jurisdiction=jurisdiction, url=url
        )

    form_hint = (
        "This PDF looks like an application/registration form. "
        "Write a useful English summary that answers: (1) what form this is, "
        "(2) what it is for / who files it, (3) what information and supporting "
        "documents the applicant must provide. Never paste blank lines, "
        "underscores, or 'click here'."
        if looks_like_form(title, snippet)
        else (
            "Write a useful English summary of what the document is and what it "
            "is for. Ignore table-of-contents dotted leaders and 'click here' link text."
        )
    )
    system = (
        "You are Eva, a regulatory research analyst for BCI RegIntel. "
        "Summarize legal/regulatory PDFs accurately in English. "
        + form_hint
        + " Reply with ONLY valid JSON (no markdown fences) with keys: "
        "summary (string, 3-6 sentences), "
        "key_points (array of 3-8 short strings), "
        "topics (array of 2-6 short topic tags), "
        "document_type (one of: form, bill, amendment, regulation, gazette, "
        "report, guidance, notice, other)."
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
        "summary": str(data.get("summary") or "").strip()
        or extractive_summary(
            title=title, text=snippet, jurisdiction=jurisdiction, url=url
        )["summary"],
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
        passages = c.get("passages") or []
        pass_txt = ""
        if passages:
            bits = []
            for p in passages[:3]:
                if isinstance(p, dict):
                    bits.append(str(p.get("text") or "")[:500])
                else:
                    bits.append(str(p)[:500])
            pass_txt = "\nPassages from PDF:\n- " + "\n- ".join(b for b in bits if b)
        blocks.append(
            f"[{i}] Title: {c.get('title')}\n"
            f"Jurisdiction: {c.get('jurisdiction')}\n"
            f"URL: {c.get('url') or c.get('open_url')}\n"
            f"Summary: {c.get('summary')}\n"
            f"Key points: {'; '.join(c.get('key_points') or [])}"
            f"{pass_txt}"
        )

    client = get_client()
    if client is None:
        # Offline synthesis — ChatGPT-style bullets from key points + passages
        lines = [
            "I searched our PDF library (not the open web) and found these relevant sources:\n",
            "Answer:",
        ]
        for i, c in enumerate(contexts[:6], 1):
            pts = c.get("key_points") or []
            if pts:
                for p in pts[:2]:
                    lines.append(f"• [{i}] {p}")
            else:
                lines.append(f"• [{i}] {(c.get('summary') or '')[:260]}")
            for p in (c.get("passages") or [])[:1]:
                t = p.get("text") if isinstance(p, dict) else str(p)
                if t:
                    lines.append(f"  “{str(t)[:280]}”")
        lines.append("\nReferences:")
        for cit in citations:
            lines.append(f"[{cit['n']}] {cit.get('title')} — {cit.get('url')}")
        lines.append(
            "\nI only use our RegIntel/SDAIA PDF index for answers."
        )
        return {"answer": "\n".join(lines), "citations": citations, "method": "retrieve_only"}

    system = (
        "You are Eva, RegIntel's PDF research assistant. "
        "You work like ChatGPT with browsing, but you ONLY search the provided PDF "
        "summaries and passages from OUR library (SDAIA / RegIntel corpus). "
        "Never invent facts from the open web or outside the sources. "
        "If the answer is not in the sources, say you don't know from the indexed PDFs. "
        "Write a clear, direct answer first, then supporting points with citations [1], [2]. "
        "End with a short 'References' list mapping [n] to document title and URL."
    )
    user = f"Question: {question}\n\nSources from our PDF library:\n\n" + "\n\n---\n\n".join(blocks)
    answer = chat_text(system, user, temperature=0.2, max_tokens=1400)
    return {"answer": answer, "citations": citations, "method": "llm"}


_PLACEHOLDER_TITLE = re.compile(
    r"^(click here|click here to review|click here to view.*|embedded[- ]url|"
    r"press here|read more|download|pdf|here|link)$",
    re.I,
)
_TOC_LEADER = re.compile(r"\.{4,}\s*\d+\s*$")
_TOC_ANY = re.compile(r"\.{4,}")
_FILL_BLANK = re.compile(r"_{4,}|X{6,}")
_FORM_TITLE_HINT = re.compile(
    r"\b(form|application|registration|questionnaire|declaration of interest|"
    r"requirements form)\b",
    re.I,
)
_FORM_BODY_HINT = re.compile(
    r"I the undersigned|please attach|please fill|yes\s+no\b|signature:|"
    r"\bQ\d+\s*:|commercial registration|declare hereby|"
    r"tick (?:the )?(?:box|appropriate)",
    re.I,
)


def is_placeholder_title(title: str) -> bool:
    t = re.sub(r"\s+", " ", (title or "").strip())
    return not t or bool(_PLACEHOLDER_TITLE.match(t))


def looks_like_form(title: str, text: str, url: str = "") -> bool:
    if looks_like_guideline(title, text, url):
        return False
    if _FORM_TITLE_HINT.search(title or ""):
        return True
    blob = text or ""
    if blob.count("_") >= 12:
        return True
    if re.search(r"\bFORM\b", blob[:1200]):
        return True
    return len(_FORM_BODY_HINT.findall(blob)) >= 2


def _is_toc_line(s: str) -> bool:
    """True for table-of-contents rows like 'Meteorological data ....15'."""
    if not s:
        return False
    if _TOC_ANY.search(s) or _TOC_LEADER.search(s):
        return True
    if re.search(r"\s\.{3,}\s*\d+\s*$", s):
        return True
    # leftover after stripping leaders: short heading + page number
    if re.search(r"\s+\d{1,3}\s*$", s) and len(s) < 80 and s.count(" ") <= 10:
        if re.search(r"(contents|preface|acknowledgements|how to |data$)", s, re.I):
            return True
    return False


def _strip_form_noise(s: str) -> str:
    s = _FILL_BLANK.sub(" ", s)
    s = _TOC_LEADER.sub("", s)
    s = re.sub(r"[.]{5,}", " ", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip(" \t-–—.,")


def looks_like_guideline(title: str, text: str, url: str = "") -> bool:
    blob = f"{title}\n{url}\n{(text or '')[:4000]}"
    if re.search(r"Desert Locust Guidelines|\bDLG\d", blob, re.I):
        return True
    if re.search(r"\bPREFACE\b", text or "") and re.search(r"\bthis guideline is intended\b", text or "", re.I):
        return True
    return False


def _clean_para(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    s = re.sub(r"(?i)^(preface|introduction|acknowledgements)\s+", "", s)
    return s


def _volume_intro_paragraph(text: str) -> str:
    """Body intro — last 'This guideline is intended…', not the series preface."""
    hits = list(
        re.finditer(
            r"This guideline is intended.{80,700}?(?:\.|\n\n)",
            text or "",
            flags=re.I | re.S,
        )
    )
    if not hits:
        return ""
    return _clean_para(hits[-1].group(0))


def guideline_summary(
    *,
    title: str,
    text: str,
    jurisdiction: str = "",
    url: str = "",
) -> dict[str, Any]:
    """Volume-specific summary from the real introduction, never the shared preface or TOC."""
    doc_title = _first_document_title("", text, url)
    if not doc_title or is_placeholder_title(doc_title) or re.search(r"^347 |DLG", doc_title, re.I):
        doc_title = "Desert Locust Guidelines"

    volume = ""
    for raw in (text or "").splitlines()[:25]:
        line = _strip_form_noise(raw)
        if re.match(r"^\d+\.\s+[A-Za-z].{4,60}$", line) and not _is_toc_line(raw):
            volume = line
            break
    topic = re.sub(r"^\d+\.\s*", "", volume).strip() if volume else ""
    display = f"{doc_title}: {volume}" if volume and volume.lower() not in doc_title.lower() else doc_title

    intro = _volume_intro_paragraph(text)
    # Skip the series-wide plague preface if it leaked in
    if re.search(r"plague of 1986", intro, re.I):
        intro = ""

    steps = [
        _clean_para(m)
        for m in re.findall(r"Step\s+\d+\.\s*(.{40,260})", text or "", flags=re.I | re.S)
    ]
    steps = [s for s in steps if s and not _is_toc_line(s)][:6]

    data_types = ""
    m = re.search(
        r"four primary types of data are required:\s*([^\.]+)",
        text or "",
        flags=re.I,
    )
    if m:
        data_types = _clean_para(m.group(1))

    officer = bool(re.search(r"Locust Information Officer", text or ""))
    who = (
        "the national Locust Information Officer at Locust Unit headquarters"
        if officer
        else "national and international locust survey and control staff"
    )

    parts = [f"{display} (FAO, 2nd edition 2001)."]
    if intro:
        parts.append(intro)
    elif topic:
        parts.append(
            f"This volume is the practical handbook on {topic.lower()} for {who}."
        )
    else:
        parts.append(f"FAO handbook for {who}.")

    if officer and topic and "information" in topic.lower():
        parts.append(
            "It teaches how to turn field reports, weather data and FAO bulletins "
            "into a situation assessment and a forecast so managers can decide "
            "where to survey, what to control first, and when to request help."
        )
    if data_types:
        parts.append(
            f"Four data types are required, each with a date and location: {data_types}."
        )
    if steps:
        parts.append("National process: " + " ".join(f"({i}) {s}" for i, s in enumerate(steps, 1)))

    summary = " ".join(parts)
    summary = re.sub(r"\s+", " ", summary).strip()

    points: list[str] = []
    if volume:
        points.append(f"What it is: FAO Desert Locust Guidelines, {volume}.")
    points.append(f"Who it is for: {who}.")
    if data_types:
        points.append("Required data: " + data_types + " (each with date and coordinates).")
    if steps:
        points.extend(steps[:4])
    if re.search(r"Desert Locust Information Service|DLIS", text or ""):
        points.append(
            "Send survey/control results to FAO DLIS in Rome within five days "
            "(weekly if locusts are present; monthly even if none)."
        )

    return {
        "summary": summary[:1800],
        "key_points": points[:8],
        "topics": ["desert locust", "forecasting", "information", "FAO", "MEWA"],
        "document_type": "guidance",
        "method": "extractive_guideline",
        "display_title": display,
    }


_FIELD_LABELS = {
    "company name",
    "national address",
    "email",
    "district",
    "city",
    "district city",
    "phone",
    "mobile phone",
    "mobile",
    "contact name",
    "p.o. box",
    "p.o. box / zip code phone",
    "zip code",
    "signature",
    "date",
    "position",
    "yes no",
}


def _heading_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = _strip_form_noise(raw)
        if not line or len(line) > 80:
            continue
        if re.match(r"Q\d+", line, re.I) or re.search(r"declaration of interest", line, re.I):
            break
        letters = [c for c in line if c.isalpha()]
        if len(letters) < 3:
            continue
        if sum(c.isupper() for c in letters) / len(letters) < 0.75:
            continue
        if re.search(r"page \d+|ring road|sunday to thursday|@|http", line, re.I):
            continue
        titled = line.title() if line.isupper() else line
        if titled.lower() in _FIELD_LABELS:
            continue
        if titled not in out:
            out.append(titled)
        if len(out) >= 6:
            break
    return out


def _first_document_title(title: str, text: str, url: str) -> str:
    if title and not is_placeholder_title(title) and not title.lower().endswith(".pdf"):
        return title
    skip = re.compile(
        r"all rights reserved|copyright|reproduction|designations employed|"
        r"^fao\b|page \d+|preface$|contents$|acknowledgements$",
        re.I,
    )
    for raw in (text or "").splitlines()[:16]:
        line = _strip_form_noise(raw)
        if not (6 <= len(line) <= 90):
            continue
        if skip.search(line):
            continue
        letters = [c for c in line if c.isalpha()]
        if len(letters) < 4:
            continue
        return line
    stem = Path_stem_from_url(url)
    if stem:
        return stem
    return title or "PDF"


def _authority_name(jurisdiction: str, text: str) -> str:
    m = re.search(
        r"Ministry of [A-Za-z, ]{6,80}|Saudi [A-Za-z ]{4,60} Authority",
        text or "",
    )
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip(" ,")
    j = (jurisdiction or "").strip()
    if " - " in j:
        return j.split(" - ", 1)[-1].strip()
    return j or "the issuing authority"


def _required_documents(text: str) -> list[str]:
    docs: list[str] = []
    for raw in (text or "").splitlines():
        line = _strip_form_noise(raw)
        if not line:
            continue
        if re.search(
            r"please attach|attach(?:ed)? copy|supporting documents|"
            r"must (?:submit|attach|provide|enclose)|copy of the",
            line,
            re.I,
        ):
            cleaned = re.sub(r"(?i)^please attach(?:ed)?\s*", "", line).strip(" .")
            if cleaned and cleaned.lower() not in {d.lower() for d in docs}:
                docs.append(cleaned)
    return docs[:8]


def _form_questions(text: str) -> list[str]:
    qs: list[str] = []
    for raw in (text or "").splitlines():
        line = _strip_form_noise(raw)
        m = re.match(r"(Q\d+)\s*[:.\-]?\s*(.+)", line, re.I)
        if not m:
            continue
        q = re.sub(r"\s+", " ", m.group(2)).strip(" .")
        if 8 <= len(q) <= 160 and q not in qs:
            qs.append(q)
    return qs[:10]


def _purpose_from_text(text: str, headings: list[str]) -> str:
    cleaned = _strip_form_noise(re.sub(r"\s+", " ", text or ""))
    m = re.search(
        r"declare hereby the intention.{0,80}to apply for (?:a |an )?(.{8,80}?)(?: and |\.|,)",
        cleaned,
        re.I,
    )
    if m:
        return "Apply for " + m.group(1).strip()
    m = re.search(
        r"to apply for (?:a |an )?(.{8,80}?)(?: and |\.|,)",
        cleaned,
        re.I,
    )
    if m:
        return "Apply for " + m.group(1).strip()
    joined = " ".join(headings).lower()
    if "qualification" in joined and "water audit" in joined:
        return "Qualify a company to perform water audits (leakage detection) for MEWA"
    if "registration" in joined:
        return "Register the applicant with the authority"
    if "requirements" in joined:
        return "Show that the applicant meets the authority's qualification requirements"
    return ""


def form_summary(
    *,
    title: str,
    text: str,
    jurisdiction: str = "",
    url: str = "",
) -> dict[str, Any]:
    """Describe a fill-in form: what it is, purpose, and required documents."""
    headings = _heading_lines(text)
    form_line = next((h for h in headings if re.search(r"\bform\b", h, re.I)), None)
    prefix = [
        h
        for h in headings
        if re.search(r"water audit|qualification", h, re.I) and not re.search(r"\bform\b", h, re.I)
    ]
    if form_line:
        form_name = " ".join(prefix[:2] + [form_line])
    else:
        name_bits = [
            h
            for h in headings
            if re.search(r"form|qualification|registration|requirement|audit|application", h, re.I)
        ]
        form_name = " ".join(name_bits[:3]).strip() or " ".join(headings[:3]).strip()
    if not form_name or is_placeholder_title(form_name):
        stem = re.sub(r"[_-]+", " ", Path_stem_from_url(url) or "")
        form_name = stem or re.sub(r"\.pdf$", "", title or "", flags=re.I)
    form_name = re.sub(r"\s+", " ", form_name).strip(" .")
    authority = _authority_name(jurisdiction, text)
    purpose = _purpose_from_text(text, headings)
    docs = _required_documents(text)
    questions = _form_questions(text)
    fields = []
    for raw in (text or "").splitlines():
        line = _strip_form_noise(raw)
        if not line or len(line) > 40:
            continue
        letters = [c for c in line if c.isalpha()]
        if len(letters) < 3:
            continue
        if sum(c.isupper() for c in letters) / len(letters) < 0.8:
            continue
        titled = line.title()
        if titled in headings or titled in fields:
            continue
        if re.search(r"page |ring road|sunday|@|http|yes no", titled, re.I):
            continue
        fields.append(titled)
        if len(fields) >= 8:
            break

    who = f" issued by {authority}" if authority else ""
    purpose_bit = purpose or "collect applicant details for official processing"
    purpose_bit = purpose_bit[0].upper() + purpose_bit[1:] if purpose_bit else purpose_bit
    summary_parts = [
        f"This is the {form_name}{who}.",
        f"Purpose: {purpose_bit}.",
    ]
    if fields:
        summary_parts.append("The form asks for: " + "; ".join(fields[:8]) + ".")
    if questions:
        summary_parts.append("It also asks: " + "; ".join(questions[:4]) + ".")
    if docs:
        summary_parts.append("Documents required to complete it: " + "; ".join(docs) + ".")
    else:
        summary_parts.append(
            "Complete every field, sign the declaration, and submit any supporting "
            "certificates the form names (for example commercial registration)."
        )
    email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    if email:
        summary_parts.append(f"Submit to {email.group(0)}.")

    points = []
    if purpose:
        points.append("Purpose: " + purpose)
    if docs:
        points.extend("Attach: " + d for d in docs[:4])
    points.extend(questions[:3])
    if email:
        points.append("Submit to " + email.group(0))
    if not points:
        points = [form_name, purpose_bit]

    topics = [w for w in ("form", "application", "qualification") if w in (text or "").lower()]
    if "water" in (text or "").lower():
        topics.append("water audit")
    return {
        "summary": " ".join(summary_parts)[:1600],
        "key_points": points[:8],
        "topics": topics[:6] or ["form"],
        "document_type": "form",
        "method": "extractive_form",
        "display_title": form_name,
    }


def Path_stem_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import unquote, urlparse

        name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    except Exception:
        name = url.rsplit("/", 1)[-1]
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    name = re.sub(r"\s*\(\d+\)\s*$", "", name)
    return name.replace("%20", " ").strip()


def extractive_summary(
    *,
    title: str,
    text: str,
    jurisdiction: str = "",
    url: str = "",
) -> dict[str, Any]:
    """Heuristic summary when no LLM key is available."""
    try:
        from eva_extract import clean_extracted_text, looks_like_glyph_dump
    except ImportError:
        from collector.eva_extract import clean_extracted_text, looks_like_glyph_dump  # type: ignore

    text = clean_extracted_text(text)
    if looks_like_form(title, text, url):
        return form_summary(title=title, text=text, jurisdiction=jurisdiction, url=url)
    if looks_like_guideline(title, text, url):
        return guideline_summary(title=title, text=text, jurisdiction=jurisdiction, url=url)

    # Re-join wrapped lines so mid-sentence line breaks stay one sentence
    joined: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if buf:
                joined.append(buf)
                buf = ""
            continue
        if buf and not re.search(r"[.!?؟。:]$", buf):
            buf = buf + " " + line
        else:
            if buf:
                joined.append(buf)
            buf = line
    if buf:
        joined.append(buf)
    unwrapped = "\n".join(joined)

    # Split into sentences-ish; drop fill-in blanks and TOC dotted leaders
    chunks = re.split(r"(?<=[.!?؟。])\s+|\n+", unwrapped)
    sents = []
    for c in chunks:
        if _is_toc_line(c):
            continue
        s = _strip_form_noise(c)
        if not (40 <= len(s) <= 400):
            continue
        if looks_like_glyph_dump(s):
            continue
        if re.fullmatch(r"[.\s\d\-–—]+", s):
            continue
        if is_placeholder_title(s) or re.match(r"(?i)click here", s):
            continue
        if _is_toc_line(s) or s.count(".") > 8:
            continue
        if re.search(
            r"all rights reserved|copyright holders|reproduction and dissemination|"
            r"designations employed|without written permission|for resale or other commercial",
            s,
            re.I,
        ):
            continue
        sents.append(s)
    keywords = (
        "shall", "regulation", "amend", "act", "bill", "article", "section",
        "authority", "ministry", "license", "compliance", "tax", "bank",
        "cyber", "data", "privacy", "insurance", "securities", "competition",
        "guideline", "intended", "purpose",
        "نظام", "لائحة", "قرار", "مادة", "وزارة", "ترخيص", "ضوابط", "تعليمات",
        "البلدية", "التراخيص",
    )
    scored = []
    for s in sents:
        sl = s.lower()
        score = sum(1 for k in keywords if k.lower() in sl or k in s)
        if re.search(
            r"all rights reserved|copyright|reproduction and dissemination|"
            r"designations employed|without written permission",
            sl,
        ):
            score -= 4
        # Prefer preface/intro over later chapter body
        if unwrapped.find(s) < max(900, len(unwrapped) // 5):
            score += 2
        if re.search(r"this guideline is intended|this document (?:is|sets out)|preface", sl):
            score += 3
        scored.append((score, s))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    top = [s for _, s in scored[:5]] or sents[:3]
    nice_title = _first_document_title(title, text, url)
    if title and re.search(r"^\d|DLG|_en_|_ar_|\.pdf$", title, re.I) and len(title.split()) <= 5:
        nice_title = _first_document_title("", text, url) or nice_title
    if not top:
        return {
            "summary": (
                (nice_title + ". " if nice_title else "")
                + "Eva could not extract readable text from this PDF "
                "(custom Arabic font encoding)."
            ).strip(),
            "key_points": [],
            "topics": [],
            "document_type": "other",
            "method": "extractive_unreadable",
            "display_title": nice_title,
        }
    summary = " ".join(top)[:1200]
    if nice_title and not is_placeholder_title(nice_title):
        summary = f"{nice_title}. " + summary
    words = re.findall(r"[A-Za-z]{5,}", text.lower())
    ar_words = re.findall(r"[\u0600-\u06FF]{3,}", text)
    stop = {"which", "their", "there", "these", "those", "about", "shall", "under", "would", "could", "between"}
    freq: dict[str, int] = {}
    for w in words + ar_words:
        if w in stop or w.startswith("uni"):
            continue
        freq[w] = freq.get(w, 0) + 1
    topics = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:6]]
    return {
        "summary": summary.strip(),
        "key_points": top[:5],
        "topics": topics,
        "document_type": "other",
        "method": "extractive",
        "display_title": nice_title,
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

"""Score whether a PDF is a legal/regulatory document (vs marketing, IoT, stats junk).

Used for Saudi ministry crawls so we stop filling the catalog with workshops,
IoT guides, newsletters, citizen-budget flyers, etc.
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

# Strong keep signals (EN + AR + common Latin transliterations of Arabic legal terms)
_KEEP = re.compile(
    r"""
    \b(?:
        law|laws|legal|legislation|legislat(?:ive|ion)|
        regulation|regulations|regulatory|
        decree|decrees|royal\s*decree|cabinet\s*decision|
        statute|statutes|act\b|bylaws?|by-laws?|ordinance|
        circular|circulars|directive|directives|
        resolution|resolutions|decision\s*no|
        implementing\s*regulation|executive\s*regulation|
        policy|policies|code\s*of\s*(?:conduct|practice)|
        compliance|requirements?|licensing|license\s*rules|
        framework|controls?|cybersecurity\s*controls?|
        rules|rulebook|guidelines?|
        penalties|sanctions|enforcement|violations?|
        # Latin transliterations of Arabic legal docs (optional al- prefix)
        (?:al)?nizam|(?:al)?netham|
        (?:al)?laaiha|(?:al)?la2eha|(?:al)?laiha|(?:al)?laehah|(?:al)?laayha|layh[ae]?t?|
        (?:al)?taameem|(?:al)?taamem|(?:al)?taamim|
        (?:al)?qarar|(?:al)?qaraar|(?:al)?qrar|
        (?:al)?ashtratat|(?:al)?ashtiratat|(?:al)?ishtiratat|
        (?:al)?dwabt|(?:al)?dawabet|(?:al)?dawabit|
        (?:al)?jazaat|(?:al)?jzaat|(?:al)?mkhalfat|(?:al)?mukhalafat|
        (?:al)?tanfeeth|(?:al)?tanfidh|(?:al)?tanzim|(?:al)?tanzem|
        (?:al)?_?qwbat|(?:al)?uqubat
    )\b
    |
    # Arabic without word boundaries (Arabic doesn't use \b well)
    (?:نظام|أنظمة|لائحة|اللوائح|قرار|قرارات|مرسوم|تعميم|تعاميم|
       تشريع|قانون|ضوابط|اشتراطات|تعليمات|تنفيذية|تنظيم|
       عقوبات|مخالفات|ترخيص|تراخيص|حوكمة|سياسة|سياسات)
    """,
    re.I | re.X | re.U,
)

# Hard reject — marketing / ops / tech fluff that ministries publish as PDFs
_REJECT = re.compile(
    r"""
    \b(?:
        iot|internet\s*of\s*things|cgiot|cgio\s*t|
        brochure|flyer|leaflet|poster|infographic|
        workshop|workshops|training\s*course|training-courses|
        conference|webinar|event\s*agenda|media\s*kit|
        newsletter|press\s*release|news\s*bulletin|
        white\s*paper|whitepaper|
        annual\s*report|quarterly\s*report|
        parks?\s*and\s*green|green\s*spaces|
        owned\s*and\s*leased|citizen\s*ver|
        journey\s*information|awareness|
        presentation|powerpoint|slideshow|
        marketing|promotional|tourism|tour\s*packet|
        # social / product fluff
        social[-_\s]?media[-_\s]?standard|
        virtualization|proxy\s*template
    )\b
    |
    (?:
        نشرة\s*دورية|ورشة|مؤتمر|دورة\s*تدريبية|
        تقرير\s*الاجراءات|تقرير\s*الإجراءات|ملاحظات\s*المستفيدين|
        التوثيق\s*الاعلامي|التوثيق\s*الإعلامي|
        # actuarial review packs (IA dumps) — not primary law
        تقارير?\s*الإ?كتوار|مراجعة\s*الإ?حتياطيات|
        # budget citizen copies / generic quarterly budget slides
        نسخة\s*المواطن
    )
    """,
    re.I | re.X | re.U,
)

# HTML page paths worth visiting first on ministry sites
_LEGAL_PATH = re.compile(
    r"""
    (?:
        /laws?(?:/|$)|/legislation|/regulations?|/legal|
        /circulars?|/decrees?|/policies|/policy|
        /rules|/bylaws?|/compliance|/licensing|
        /systems?(?:/|$)|/statutes?|/documents?/legal|
        /docslibrary|/library/laws|/e-services/regulations|
        # Arabic path segments (percent-encoded or plain)
        نظام|لائحة|تشريع|قانون|تعميم|قرار|ضوابط|اشتراطات|
        %D9%86%D8%B8%D8%A7%D9%85|%D9%84%D8%A7%D8%A6%D8%AD%D8%A9
    )
    """,
    re.I | re.X | re.U,
)

_JUNK_PATH = re.compile(
    r"""
    (?:
        /news(?:/|$)|/media(?:/|$)|/press|/events?(?:/|$)|
        /careers?|/jobs|/tenders?(?:/|$)|/procurement|
        /gallery|/videos?|/blog|/social|
        /about(?:-us)?(?:/|$)|/contact|/faq|
        /training|/workshop|/conference|
        portalindicators|/researchs/portal
    )
    """,
    re.I | re.X,
)

# Default seeds appended for ministry homepage crawls (relative paths)
MINISTRY_LEGAL_SEED_PATHS = [
    "/en/laws",
    "/ar/laws",
    "/en/regulations",
    "/ar/regulations",
    "/en/legislation",
    "/ar/legislation",
    "/en/policies",
    "/ar/policies",
    "/en/circulars",
    "/ar/circulars",
    "/laws",
    "/regulations",
    "/legislation",
    "/policies",
    "/documents",
    "/library",
    "/docslibrary",
    "/en/documents",
    "/ar/documents",
    "/en/systems",
    "/ar/systems",
    "/en/rules",
    "/ar/rules",
]


def _blob(url: str = "", title: str = "", filename: str = "", text: str = "") -> str:
    path = unquote(urlparse(url or "").path or "")
    name = unquote(filename or (path.rsplit("/", 1)[-1] if path else ""))
    raw = " ".join(
        [
            url or "",
            path,
            name,
            title or "",
            text or "",
        ]
    )
    # Protect IoT token before camelCase (IoT / CGIoT)
    raw = re.sub(r"IoT", "§IOT§", raw, flags=re.I)
    # camelCase → words (BankingControlLaw → Banking Control Law)
    raw = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw)
    raw = raw.lower()
    # underscores/hyphens in filenames break \b — normalize to spaces
    raw = re.sub(r"[_\-./]+", " ", raw)
    raw = raw.replace("§iot§", " iot ")
    return raw


def is_junk_page(url: str) -> bool:
    """HTML pages we should not BFS into (news, careers, media)."""
    path = unquote(urlparse(url or "").path or "")
    return bool(_JUNK_PATH.search(path))


def is_legal_priority_page(url: str) -> bool:
    path = unquote(urlparse(url or "").path or "")
    return bool(_LEGAL_PATH.search(path) or _LEGAL_PATH.search(url or ""))


def regulatory_score(
    *,
    url: str = "",
    title: str = "",
    filename: str = "",
    text: str = "",
) -> int:
    """
    Higher = more likely a law/regulation PDF.
    Returns negative for hard rejects.
    """
    b = _blob(url, title, filename, text)
    if not b.strip():
        return 0
    if _REJECT.search(b):
        return -100
    score = 0
    if _KEEP.search(b):
        score += 40
    # path hints
    path = unquote(urlparse(url or "").path or "")
    if _LEGAL_PATH.search(path) or _LEGAL_PATH.search(url or ""):
        score += 25
    if _JUNK_PATH.search(path):
        score -= 30
    # filename alone with legal AR/EN tokens
    fname = unquote(filename or path.rsplit("/", 1)[-1] if path else "")
    if _KEEP.search(fname):
        score += 20
    # generic link text is useless — don't reward "PDF" / "download" / "embedded-url"
    t = (title or text or "").strip().lower()
    if t in ("", "pdf", "download", "embedded-url", "quoted-path", "show", "تنزيل الملف", "المستند", "ملف منفصل"):
        pass
    elif _KEEP.search(t):
        score += 15
    return score


def is_regulatory_pdf(
    *,
    url: str = "",
    title: str = "",
    filename: str = "",
    text: str = "",
    min_score: int = 15,
) -> bool:
    return regulatory_score(url=url, title=title, filename=filename, text=text) >= min_score


def filter_regulatory_docs(
    docs: list,
    *,
    min_score: int = 15,
    url_attr: str = "url",
    text_attr: str = "text",
) -> tuple[list, list]:
    """Split FoundDoc-like objects into (keep, reject)."""
    keep, reject = [], []
    for d in docs:
        url = getattr(d, url_attr, None) or (d.get(url_attr) if isinstance(d, dict) else "") or ""
        text = getattr(d, text_attr, None) or (d.get(text_attr) if isinstance(d, dict) else "") or ""
        sc = regulatory_score(url=url, title=text, text=text)
        if sc >= min_score:
            keep.append(d)
        else:
            reject.append((d, sc))
    # sort keep by score desc
    keep.sort(
        key=lambda d: regulatory_score(
            url=getattr(d, "url", None) or "",
            title=getattr(d, "text", None) or "",
            text=getattr(d, "text", None) or "",
        ),
        reverse=True,
    )
    return keep, reject

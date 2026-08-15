#!/usr/bin/env python3
"""Allowlist for the Saudi public site — original ministry sheet + SDAIA/TGA/MC/MEWA."""
from __future__ import annotations

ALLOWED_HOST_MARKERS = (
    "sdaia.gov.sa",
    "dgp.sdaia",
    "tga.gov.sa",
    "mc.gov.sa",
    "mewa.gov.sa",
    "momah.gov.sa",
    "mof.gov.sa",
    "nca.gov.sa",
    "ia.gov.sa",
    "socpa.org.sa",
    "moi.gov.sa",
    "nazaha.gov.sa",
    "sama.gov.sa",
    "rulebook.sama",
    "moj.gov.sa",
    "gac.gov.sa",
    "cst.gov.sa",
    "cma.org.sa",
    "saudiexchange.sa",
    "gosi.gov.sa",
    "saso.gov.sa",
    "saip.gov.sa",
    "zatca.gov.sa",
)

ALLOWED_JURISDICTION_MARKERS = (
    "SDAIA",
    "TGA",
    "MEWA",
    "MOMAH",
    "MOF",
    "NCA",
    "SOCPA",
    "MOI",
    "Nazaha",
    "NAZAHA",
    "SAMA",
    "MOJ",
    "GAC",
    "CST",
    "CMA",
    "Tadawul",
    "TADAWUL",
    "GOSI",
    "SASO",
    "SAIP",
    "ZATCA",
    "Ministry of Commerce",
    "Transport General",
    "Environment, Water",
    "Saudi Arabia - MC",
    "Saudi Arabia - TGA",
    "Saudi Arabia - MEWA",
    "Saudi Arabia - SDAIA",
    "Saudi Arabia - IA",
    "Saudi Arabia - MoC",
)

AUTHORITIES = [
    {"code": "SDAIA", "name": "Saudi Data and Artificial Intelligence Authority (SDAIA)", "url": "https://sdaia.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - SDAIA", "crawl_url": "https://sdaia.gov.sa"},
    {"code": "MEWA", "name": "Ministry of Environment, Water and Agriculture (MEWA)", "url": "https://mewa.gov.sa", "country": "Saudi Arabia", "authority_type": "Ministry", "label": "Saudi Arabia - MEWA", "crawl_url": "https://mewa.gov.sa"},
    {"code": "MC", "name": "Ministry of Commerce (MC)", "url": "https://mc.gov.sa", "country": "Saudi Arabia", "authority_type": "Ministry", "label": "Saudi Arabia - MC", "crawl_url": "https://mc.gov.sa"},
    {"code": "TGA", "name": "Transport General Authority (TGA)", "url": "https://tga.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - TGA", "crawl_url": "https://tga.gov.sa"},
    {"code": "MOMAH", "name": "Ministry of Municipalities and Housing (MOMAH)", "url": "https://momah.gov.sa", "country": "Saudi Arabia", "authority_type": "Ministry", "label": "Saudi Arabia - MOMAH", "crawl_url": "https://momah.gov.sa"},
    {"code": "MOF", "name": "Ministry of Finance (MOF)", "url": "https://www.mof.gov.sa", "country": "Saudi Arabia", "authority_type": "Ministry", "label": "Saudi Arabia - MOF", "crawl_url": "https://www.mof.gov.sa"},
    {"code": "NCA", "name": "National Cybersecurity Authority (NCA)", "url": "https://nca.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - NCA", "crawl_url": "https://nca.gov.sa"},
    {"code": "IA", "name": "Insurance Authority (IA)", "url": "https://ia.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - IA", "crawl_url": "https://ia.gov.sa"},
    {"code": "SOCPA", "name": "Saudi Organization for Chartered and Professional Accountants (SOCPA)", "url": "https://socpa.org.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - SOCPA", "crawl_url": "https://socpa.org.sa"},
    {"code": "MOI", "name": "Ministry of Interior (MOI)", "url": "https://www.moi.gov.sa", "country": "Saudi Arabia", "authority_type": "Ministry", "label": "Saudi Arabia - MOI", "crawl_url": "https://www.moi.gov.sa"},
    {"code": "NAZAHA", "name": "Oversight and Anti-Corruption Authority (Nazaha)", "url": "https://nazaha.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - Nazaha", "crawl_url": "https://nazaha.gov.sa"},
    {"code": "SAMA", "name": "Saudi Central Bank (SAMA)", "url": "https://rulebook.sama.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - SAMA", "crawl_url": "https://rulebook.sama.gov.sa/en"},
    {"code": "MOJ", "name": "Ministry of Justice (MOJ)", "url": "https://www.moj.gov.sa", "country": "Saudi Arabia", "authority_type": "Ministry", "label": "Saudi Arabia - MOJ", "crawl_url": "https://www.moj.gov.sa"},
    {"code": "GAC", "name": "General Authority of Civil Aviation (GAC)", "url": "https://gac.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - GAC", "crawl_url": "https://gac.gov.sa"},
    {"code": "CST", "name": "Communications, Space and Technology Commission (CST)", "url": "https://www.cst.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - CST", "crawl_url": "https://www.cst.gov.sa"},
    {"code": "CMA", "name": "Capital Market Authority (CMA)", "url": "https://cma.org.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - CMA", "crawl_url": "https://cma.org.sa"},
    {"code": "TADAWUL", "name": "Saudi Exchange (Tadawul)", "url": "https://www.saudiexchange.sa", "country": "Saudi Arabia", "authority_type": "Exchange", "label": "Saudi Arabia - Tadawul", "crawl_url": "https://www.saudiexchange.sa"},
    {"code": "GOSI", "name": "General Organization for Social Insurance (GOSI)", "url": "https://www.gosi.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - GOSI", "crawl_url": "https://www.gosi.gov.sa"},
    {"code": "SASO", "name": "Saudi Standards, Metrology and Quality Organization (SASO)", "url": "https://www.saso.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - SASO", "crawl_url": "https://www.saso.gov.sa"},
    {"code": "SAIP", "name": "Saudi Authority for Intellectual Property (SAIP)", "url": "https://www.saip.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - SAIP", "crawl_url": "https://www.saip.gov.sa"},
    {"code": "ZATCA", "name": "Zakat, Tax and Customs Authority (ZATCA)", "url": "https://zatca.gov.sa", "country": "Saudi Arabia", "authority_type": "Authority", "label": "Saudi Arabia - ZATCA", "crawl_url": "https://zatca.gov.sa"},
]


def _blob(p: dict) -> str:
    return " ".join(
        [
            str(p.get("jurisdiction") or ""),
            str(p.get("host") or ""),
            str(p.get("url") or p.get("open_url") or ""),
            str(p.get("source_page") or ""),
            str(p.get("label") or ""),
        ]
    )


def is_allowed_ministry_row(p: dict) -> bool:
    b = _blob(p)
    bl = b.lower()
    if any(m.lower() in bl for m in ALLOWED_HOST_MARKERS):
        return True
    if any(m in b for m in ALLOWED_JURISDICTION_MARKERS):
        return True
    return False


def normalize_jurisdiction(p: dict) -> str:
    bl = _blob(p).lower()
    if "sdaia" in bl or "dgp.sdaia" in bl:
        return "Saudi Arabia - SDAIA"
    if "tga.gov" in bl or "saudi arabia - tga" in bl:
        return "Saudi Arabia - TGA"
    if "mewa.gov" in bl or "saudi arabia - mewa" in bl:
        return "Saudi Arabia - MEWA"
    if "mc.gov" in bl or "saudi arabia - mc" in bl or "ministry of commerce" in bl:
        return "Saudi Arabia - MC"
    if "momah.gov" in bl:
        return "Saudi Arabia - MOMAH"
    if "mof.gov" in bl:
        return "Saudi Arabia - MOF"
    if "nca.gov" in bl:
        return "Saudi Arabia - NCA"
    if "ia.gov" in bl and "sdaia" not in bl:
        return "Saudi Arabia - IA"
    if "socpa.org" in bl:
        return "Saudi Arabia - SOCPA"
    if "moi.gov" in bl:
        return "Saudi Arabia - MOI"
    if "nazaha.gov" in bl:
        return "Saudi Arabia - Nazaha"
    if "sama.gov" in bl or "rulebook.sama" in bl:
        return "Saudi Arabia - SAMA"
    if "moj.gov" in bl:
        return "Saudi Arabia - MOJ"
    if "gac.gov" in bl:
        return "Saudi Arabia - GAC"
    if "cst.gov" in bl:
        return "Saudi Arabia - CST"
    if "cma.org" in bl or "cma.gov" in bl:
        return "Saudi Arabia - CMA"
    if "saudiexchange" in bl or "tadawul" in bl:
        return "Saudi Arabia - Tadawul"
    if "gosi.gov" in bl:
        return "Saudi Arabia - GOSI"
    if "saso.gov" in bl:
        return "Saudi Arabia - SASO"
    if "saip.gov" in bl:
        return "Saudi Arabia - SAIP"
    if "zatca.gov" in bl:
        return "Saudi Arabia - ZATCA"
    j = str(p.get("jurisdiction") or "").strip()
    return j or "Saudi Arabia"

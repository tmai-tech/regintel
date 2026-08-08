#!/usr/bin/env python3
"""Shared allowlist for the multi-ministry Saudi public site (SDAIA + TGA + MC + MEWA)."""
from __future__ import annotations

# Hosts / path tokens that identify allowed authorities (case-insensitive).
# User asked for tga.gov.sa, mc.ga.sa (treated as mc.gov.sa), mewa.gov.sa + current SDAIA.
ALLOWED_HOST_MARKERS = (
    "sdaia.gov.sa",
    "dgp.sdaia",
    "tga.gov.sa",
    "mc.gov.sa",
    "mewa.gov.sa",
)

# Jurisdiction label tokens
ALLOWED_JURISDICTION_MARKERS = (
    "SDAIA",
    "TGA",
    "MEWA",
    "Ministry of Commerce",
    "Transport General",
    "Environment, Water",
    "Saudi Arabia - MC",
    "Saudi Arabia - TGA",
    "Saudi Arabia - MEWA",
    "Saudi Arabia - SDAIA",
)

AUTHORITIES = [
    {
        "code": "SDAIA",
        "name": "Saudi Data and Artificial Intelligence Authority (SDAIA)",
        "url": "https://sdaia.gov.sa",
        "country": "Saudi Arabia",
        "authority_type": "Authority",
        "label": "Saudi Arabia - SDAIA",
        "crawl_url": "https://sdaia.gov.sa",
    },
    {
        "code": "TGA",
        "name": "Transport General Authority (TGA)",
        "url": "https://tga.gov.sa",
        "country": "Saudi Arabia",
        "authority_type": "Authority",
        "label": "Saudi Arabia - TGA",
        "crawl_url": "https://tga.gov.sa",
    },
    {
        "code": "MC",
        "name": "Ministry of Commerce (MC)",
        "url": "https://mc.gov.sa",
        "country": "Saudi Arabia",
        "authority_type": "Ministry",
        "label": "Saudi Arabia - MC",
        "crawl_url": "https://mc.gov.sa",
    },
    {
        "code": "MEWA",
        "name": "Ministry of Environment, Water and Agriculture (MEWA)",
        "url": "https://mewa.gov.sa",
        "country": "Saudi Arabia",
        "authority_type": "Ministry",
        "label": "Saudi Arabia - MEWA",
        "crawl_url": "https://mewa.gov.sa",
    },
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
    """Map a PDF row to a stable jurisdiction label."""
    bl = _blob(p).lower()
    if "sdaia" in bl or "dgp.sdaia" in bl:
        return "Saudi Arabia - SDAIA"
    if "tga.gov" in bl or "saudi arabia - tga" in bl:
        return "Saudi Arabia - TGA"
    if "mewa.gov" in bl or "saudi arabia - mewa" in bl:
        return "Saudi Arabia - MEWA"
    if "mc.gov" in bl or "saudi arabia - mc" in bl or "ministry of commerce" in bl:
        return "Saudi Arabia - MC"
    j = str(p.get("jurisdiction") or "").strip()
    return j or "Saudi Arabia"

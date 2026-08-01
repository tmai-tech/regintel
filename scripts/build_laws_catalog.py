#!/usr/bin/env python3
"""Build enriched laws_catalog.json for web + Android from tracking, updates, primary sources.

Each row includes:
  name, summary, country, level (Federal|State), level_detail, law_area, topic,
  link, authority, authority_url, region, date, source, relevancy
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WEB_DATA = ROOT / "web" / "data"
ANDROID_ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets"

# Subnational units (US states, CA provinces, AU states, UK nations, …)
CA_PROVINCES = {
    "ontario", "quebec", "british columbia", "alberta", "manitoba", "saskatchewan",
    "nova scotia", "new brunswick", "newfoundland", "newfoundland and labrador",
    "prince edward island", "yukon", "northwest territories", "nunavut",
}
AU_STATES = {
    "new south wales", "victoria", "queensland", "south australia", "western australia",
    "tasmania", "australian capital territory", "northern territory",
}
UK_NATIONS = {"england", "scotland", "wales", "northern ireland"}
US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
    "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "district of columbia", "dc",
}
STATE_HINTS = CA_PROVINCES | AU_STATES | UK_NATIONS | US_STATES

COUNTRY_ALIASES = {
    "us": "US",
    "usa": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "united states": "US",
    "uk": "UK",
    "u.k.": "UK",
    "united kingdom": "UK",
    "eu": "EU",
    "european union": "EU",
    "hongkong": "Hong Kong",
    "hong kong": "Hong Kong",
    "korea": "Korea",
    "south korea": "Korea",
    "republic of korea": "Korea",
    "phillipines": "Philippines",
    "philippines": "Philippines",
    "uae": "UAE",
    "viet nam": "Vietnam",
}


def load(name: str):
    path = DATA / name
    if not path.exists():
        path = WEB_DATA / name
    if not path.exists():
        return [] if name.endswith(".json") else {}
    return json.loads(path.read_text(encoding="utf-8"))


def host_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        h = urlparse(url.strip()).hostname or ""
        return h.lower().removeprefix("www.")
    except Exception:
        return ""


def normalize_law_area(raw: str | None) -> str:
    if not raw:
        return ""
    s = str(raw).replace("\n", " ").replace(";", ",")
    s = re.sub(r"\s+", " ", s).strip()
    # normalize common variants
    parts = []
    for p in s.split(","):
        p = p.strip()
        if not p:
            continue
        low = p.lower()
        if low in ("capital markets", "capital market"):
            p = "Capital"
        elif low in ("private markets", "private market"):
            p = "Private"
        elif low == "private & capital":
            parts.extend(["Private", "Capital"])
            continue
        elif low == "capital & private":
            parts.extend(["Capital", "Private"])
            continue
        parts.append(p)
    # unique preserve order
    out = []
    seen = set()
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return ", ".join(out)


def normalize_country_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    return COUNTRY_ALIASES.get(n.lower(), n)


def parse_jurisdiction(raw: str | None, fed_or_state: str | None = None) -> dict:
    """Return country, level (Federal|State), level_detail."""
    s = (raw or "").strip()
    fos = (fed_or_state or "").strip()

    if fos:
        if fos.lower() == "federal":
            country = normalize_country_name(
                re.sub(r"\s*[-–—]?\s*federal\b", "", s, flags=re.I).strip() or s
            )
            return {"country": country, "level": "Federal", "level_detail": "Federal"}
        # fos is a state/province name
        parent = parent_country_for_state(fos) or parent_country_for_state(s) or normalize_country_name(s)
        return {
            "country": parent if parent and parent.lower() != fos.lower() else normalize_country_name(s) or parent,
            "level": "State",
            "level_detail": fos,
        }

    if not s:
        return {"country": "", "level": "Federal", "level_detail": "Federal"}

    m = re.match(r"^(.+?)\s*[-–—]\s*federal$", s, re.I)
    if m:
        return {
            "country": normalize_country_name(m.group(1)),
            "level": "Federal",
            "level_detail": "Federal",
        }
    if re.search(r"\bfederal\b", s, re.I):
        country = re.sub(r"\s*[-–—]?\s*federal\b", "", s, flags=re.I).strip() or s
        return {
            "country": normalize_country_name(country),
            "level": "Federal",
            "level_detail": "Federal",
        }

    low = s.lower().strip()
    if low in STATE_HINTS or any(low == h for h in STATE_HINTS):
        return {
            "country": parent_country_for_state(s),
            "level": "State",
            "level_detail": s,
        }

    # "US - New York" / "Canada - Ontario"
    m2 = re.match(r"^(.+?)\s*[-–—]\s*(.+)$", s)
    if m2:
        left, right = m2.group(1).strip(), m2.group(2).strip()
        if right.lower() in STATE_HINTS or left.lower() in ("us", "usa", "canada", "australia", "uk"):
            if right.lower() == "federal":
                return {
                    "country": normalize_country_name(left),
                    "level": "Federal",
                    "level_detail": "Federal",
                }
            return {
                "country": normalize_country_name(left),
                "level": "State",
                "level_detail": right,
            }

    return {
        "country": normalize_country_name(s),
        "level": "Federal",
        "level_detail": "Federal",
    }


def parent_country_for_state(name: str) -> str:
    low = (name or "").lower().strip()
    if low in CA_PROVINCES:
        return "Canada"
    if low in AU_STATES:
        return "Australia"
    if low in UK_NATIONS:
        return "UK"
    if low in US_STATES:
        return "US"
    return normalize_country_name(name)


def build_authority_index(primary: list[dict]) -> dict[str, dict]:
    """host -> {name, url, jurisdiction, region}"""
    by_host: dict[str, dict] = {}
    for s in primary:
        url = (s.get("url") or "").strip()
        name = (s.get("authority") or "").strip()
        if not name or not url.startswith("http"):
            continue
        h = host_of(url)
        if not h or h in by_host:
            continue
        by_host[h] = {
            "name": name,
            "url": url,
            "jurisdiction": s.get("jurisdiction") or "",
            "region": s.get("region") or "",
        }
    return by_host


def match_authority(index: dict[str, dict], link: str) -> dict | None:
    h = host_of(link)
    if not h:
        return None
    if h in index:
        return index[h]
    parts = h.split(".")
    for i in range(1, max(len(parts) - 1, 0)):
        parent = ".".join(parts[i:])
        if parent in index:
            return index[parent]
    # suffix / prefix
    for key, val in index.items():
        if h.endswith("." + key) or key.endswith("." + h):
            return val
    # last two labels (e.g. osfi-bsif.gc.ca)
    if len(parts) >= 2:
        base = ".".join(parts[-2:])
        if base in index:
            return index[base]
    return None


def match_authority_by_name(
    primary: list[dict],
    authority_hint: str,
    country: str,
) -> dict | None:
    """When host match fails, try authority name substring within same country."""
    hint = (authority_hint or "").strip().lower()
    if len(hint) < 4:
        return None
    country_l = (country or "").lower()
    for s in primary:
        name = (s.get("authority") or "").strip()
        if not name:
            continue
        nl = name.lower()
        if hint not in nl and nl not in hint:
            continue
        jur = parse_jurisdiction(s.get("jurisdiction"))
        if country_l and jur["country"].lower() not in (country_l, "") and country_l not in jur["country"].lower():
            continue
        url = (s.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        return {"name": name, "url": url, "jurisdiction": s.get("jurisdiction") or "", "region": s.get("region") or ""}
    return None


def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip())
    # drop useless scrape labels
    if t.lower() in ("click here", "read more", "here", "pdf", "download", "link"):
        return ""
    return t


def build_summary(
    *,
    name: str,
    topic: str,
    law_area: str,
    remarks: str,
    comments: str,
    relevancy: str,
    authority: str,
    level: str,
    level_detail: str,
    country: str,
    source: str,
) -> str:
    """Human-readable summary for cards (not just raw topic dump)."""
    bits: list[str] = []

    # Prefer prose description (remarks when different from title)
    remarks_c = (remarks or "").strip()
    if remarks_c and remarks_c.lower() != (name or "").lower():
        bits.append(remarks_c)

    topic_c = (topic or "").strip()
    if topic_c and topic_c.lower() not in {b.lower() for b in bits} and topic_c.lower() != (name or "").lower():
        # keep topic list short
        topics = [t.strip() for t in re.split(r"[,;]", topic_c) if t.strip()]
        if topics:
            shown = topics[:4]
            label = ", ".join(shown)
            if len(topics) > 4:
                label += f" (+{len(topics) - 4} more)"
            bits.append(f"Topics: {label}")

    if law_area:
        bits.append(f"Law area: {law_area}")

    place = country
    if level == "State" and level_detail and level_detail != level:
        place = f"{level_detail} ({country})" if country else level_detail
    elif level == "Federal" and country:
        place = f"{country} (federal)"
    if place:
        bits.append(f"Jurisdiction: {place}")

    if authority:
        bits.append(f"Issued / tracked under: {authority}")

    comments_c = (comments or "").strip()
    if comments_c:
        bits.append(comments_c)

    if relevancy and relevancy not in ("Pending", "seed"):
        bits.append(f"Relevancy: {relevancy}")
    elif source == "collector" and relevancy == "Pending":
        bits.append("Awaiting analyst review")

    if not bits:
        return "Regulatory / legal update."
    # Join with sentence-ish separators; cap length
    summary = " · ".join(bits)
    if len(summary) > 480:
        summary = summary[:477] + "…"
    return summary


def stable_id(*parts: str) -> str:
    raw = "|".join(p or "" for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def from_update(u: dict, auth_index: dict, primary: list[dict]) -> dict | None:
    name = clean_title(u.get("title") or "") or (u.get("title") or "").strip() or "Untitled update"
    link = (u.get("link") or "").strip()
    if not link and not name:
        return None
    parsed = parse_jurisdiction(u.get("country") or u.get("jurisdiction"))
    topic = (u.get("topical_relevance") or "").strip()
    area = normalize_law_area(u.get("law_area") or u.get("segment"))
    authority = (u.get("authority") or "").strip()
    authority_url = (u.get("source_url") or "").strip()
    if not authority_url or not authority:
        matched = match_authority(auth_index, link) or match_authority(auth_index, authority_url)
        if matched:
            authority = authority or matched["name"]
            authority_url = authority_url or matched["url"]
            if not parsed["country"] and matched.get("jurisdiction"):
                parsed = parse_jurisdiction(matched["jurisdiction"])
    if not authority and link:
        matched = match_authority_by_name(primary, name, parsed["country"])
        if matched:
            authority = matched["name"]
            authority_url = matched["url"]

    relevancy = (u.get("relevancy") or "").strip()
    summary = build_summary(
        name=name,
        topic=topic,
        law_area=area,
        remarks="",
        comments="",
        relevancy=relevancy,
        authority=authority,
        level=parsed["level"],
        level_detail=parsed["level_detail"],
        country=parsed["country"],
        source="collector",
    )
    return {
        "id": u.get("id") or stable_id("upd", link, name),
        "name": name,
        "summary": summary,
        "country": parsed["country"],
        "level": parsed["level"],
        "level_detail": parsed["level_detail"],
        "law_area": area,
        "topic": topic,
        "link": link,
        "authority": authority,
        "authority_url": authority_url,
        "region": (u.get("region") or "").strip(),
        "date": (u.get("discovered_at") or "").strip(),
        "source": "collector",
        "relevancy": relevancy or "Pending",
        "alert_status": (u.get("alert_status") or "").strip(),
    }


def from_tracking(t: dict, auth_index: dict, primary: list[dict]) -> dict | None:
    remarks = (t.get("remarks") or "").strip()
    topic = (t.get("topical_relevance") or "").strip()
    name = clean_title(remarks) or remarks or topic or "Tracked update"
    link = (t.get("link") or "").strip()
    if not link and not name:
        return None
    parsed = parse_jurisdiction(t.get("country"), t.get("federal_or_state"))
    area = normalize_law_area(t.get("law_area"))
    matched = match_authority(auth_index, link)
    if not matched and remarks:
        # try extract authority-like prefix from remarks ("CSA adopts…")
        matched = match_authority_by_name(primary, remarks[:60], parsed["country"])
    authority = (matched or {}).get("name", "")
    authority_url = (matched or {}).get("url", "")
    # if match has better jurisdiction for state rows already set, keep tracking's
    region = (matched or {}).get("region", "")
    relevancy = (t.get("relevancy") or "").strip()
    comments = (t.get("comments") or "").strip()
    summary = build_summary(
        name=name,
        topic=topic,
        law_area=area,
        remarks=remarks if remarks != name else "",
        comments=comments,
        relevancy=relevancy,
        authority=authority,
        level=parsed["level"],
        level_detail=parsed["level_detail"],
        country=parsed["country"],
        source="tracking",
    )
    return {
        "id": stable_id("trk", link, name),
        "name": name,
        "summary": summary,
        "country": parsed["country"],
        "level": parsed["level"],
        "level_detail": parsed["level_detail"],
        "law_area": area,
        "topic": topic,
        "link": link,
        "authority": authority,
        "authority_url": authority_url,
        "region": region,
        "date": str(t.get("date_of_publication") or t.get("date_of_tracking") or ""),
        "source": "tracking",
        "relevancy": relevancy,
        "alert_status": (t.get("alert_status") or "").strip(),
        "tracked_by": (t.get("tracked_by") or "").strip(),
    }


def from_primary(s: dict) -> dict | None:
    """Authority / source registry row — fills Federal & State coverage for browse."""
    name = (s.get("authority") or "").strip()
    url = (s.get("url") or "").strip()
    if not name or not url.startswith("http"):
        return None
    if (s.get("status") or "active") not in ("active", "ok", ""):
        # still include broken so analysts can see them, but mark summary
        pass
    parsed = parse_jurisdiction(s.get("jurisdiction"))
    topics = s.get("topics") or []
    if isinstance(topics, str):
        topic = topics
    else:
        topic = ", ".join(str(t) for t in topics if t)
    area = normalize_law_area(s.get("segment"))
    status = (s.get("status") or "active").strip()
    auth_type = (s.get("authority_type") or "").strip()
    link_nature = (s.get("link_nature") or "").strip()
    remarks_bits = []
    if auth_type:
        remarks_bits.append(f"{auth_type} authority")
    if link_nature:
        remarks_bits.append(link_nature)
    summary = build_summary(
        name=name,
        topic=topic,
        law_area=area,
        remarks=" · ".join(remarks_bits),
        comments="" if status == "active" else f"Source status: {status}",
        relevancy="",
        authority=name,
        level=parsed["level"],
        level_detail=parsed["level_detail"],
        country=parsed["country"],
        source="source",
    )
    return {
        "id": stable_id("src", url, name),
        "name": name,
        "summary": summary,
        "country": parsed["country"],
        "level": parsed["level"],
        "level_detail": parsed["level_detail"],
        "law_area": area,
        "topic": topic[:300] if topic else "",
        "link": url,
        "authority": name,
        "authority_url": url,
        "region": (s.get("region") or "").strip(),
        "date": "",
        "source": "source",
        "relevancy": "",
        "alert_status": status,
    }


def build_catalog() -> list[dict]:
    updates = load("updates.json")
    tracking = load("tracking.json")
    primary = load("primary_sources.json")
    if not isinstance(updates, list):
        updates = []
    if not isinstance(tracking, list):
        tracking = []
    if not isinstance(primary, list):
        primary = []

    auth_index = build_authority_index(primary)
    rows: list[dict] = []
    seen: set[str] = set()

    # Prefer concrete updates / tracking over bare source rows when links collide
    for u in updates:
        row = from_update(u, auth_index, primary)
        if not row:
            continue
        key = (row["link"] or row["name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    for t in tracking:
        row = from_tracking(t, auth_index, primary)
        if not row:
            continue
        key = (row["link"] or row["name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    for s in primary:
        row = from_primary(s)
        if not row:
            continue
        key = (row["link"] or row["name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    # Updates/tracking first (have dates), then sources alphabetically by country/name
    def sort_key(r: dict):
        src_rank = 0 if r.get("source") == "collector" else 1 if r.get("source") == "tracking" else 2
        return (src_rank, -(1 if r.get("date") else 0), r.get("date") or "", r.get("country") or "", r.get("name") or "")

    rows.sort(key=sort_key)
    return rows


def write_outputs(rows: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    text = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    (DATA / "laws_catalog.json").write_text(text, encoding="utf-8")
    (WEB_DATA / "laws_catalog.json").write_text(text, encoding="utf-8")
    if ANDROID_ASSETS.is_dir():
        (ANDROID_ASSETS / "laws_catalog.json").write_text(text, encoding="utf-8")
    # also mirror source jsons into android if present
    for name in ("updates.json", "tracking.json", "primary_sources.json"):
        src = DATA / name if (DATA / name).exists() else WEB_DATA / name
        if src.exists() and ANDROID_ASSETS.is_dir():
            shutil.copy2(src, ANDROID_ASSETS / name)


def main():
    rows = build_catalog()
    write_outputs(rows)
    by_country = defaultdict(int)
    by_level = defaultdict(int)
    with_auth = sum(1 for r in rows if r.get("authority"))
    with_summary = sum(1 for r in rows if r.get("summary") and len(r["summary"]) > 20)
    for r in rows:
        by_country[r.get("country") or "?"] += 1
        by_level[r.get("level") or "?"] += 1
    print(
        json.dumps(
            {
                "laws": len(rows),
                "with_authority": with_auth,
                "with_summary": with_summary,
                "levels": dict(by_level),
                "top_countries": dict(sorted(by_country.items(), key=lambda x: -x[1])[:15]),
                "outputs": [
                    str(DATA / "laws_catalog.json"),
                    str(WEB_DATA / "laws_catalog.json"),
                    str(ANDROID_ASSETS / "laws_catalog.json") if ANDROID_ASSETS.is_dir() else None,
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

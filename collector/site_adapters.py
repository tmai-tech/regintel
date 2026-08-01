"""Jurisdiction-specific bill/amendment PDF discovery helpers."""
from __future__ import annotations

import json
import re
import time
from typing import Callable
from urllib.parse import urljoin, urlparse

FetchFn = Callable[..., tuple]  # (url, extra_headers?) -> status, ct, body, err


def _json(body: bytes | None):
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return None


def discover_extra_pdfs(
    page_url: str,
    *,
    fetch: FetchFn,
    delay: float,
    extract_links,
    looks_like_bill,
) -> list[dict]:
    host = urlparse(page_url).netloc.lower()
    out: list[dict] = []

    def add(url: str, text: str = ""):
        if not url:
            return
        if not str(url).startswith("http"):
            url = urljoin(page_url, url)
        out.append({"url": url, "text": text[:300], "is_pdf": ".pdf" in url.lower()})

    # --- UK Bills API (paginated — sites list hundreds of publications) ---
    if "bills.parliament.uk" in host or (
        "parliament.uk" in host and "bill" in page_url.lower()
    ):
        take = 50
        max_bills = 300  # ~300 bills × pubs each → can exceed 300+ PDFs on one site
        skip = 0
        bills_seen = 0
        while bills_seen < max_bills:
            api = (
                "https://bills-api.parliament.uk/api/v1/Bills"
                f"?Take={take}&Skip={skip}&SortOrder=DateUpdatedDescending"
            )
            st, _, body, err = fetch(api)
            time.sleep(delay)
            data = _json(body) if body and not err and st and st < 400 else None
            items = (data or {}).get("items") or []
            if not items:
                break
            for it in items:
                if bills_seen >= max_bills:
                    break
                bills_seen += 1
                bid = it.get("billId") or it.get("id")
                title = it.get("shortTitle") or it.get("title") or f"Bill {bid}"
                if not bid:
                    continue
                pub_url = f"https://bills-api.parliament.uk/api/v1/Bills/{bid}/Publications"
                st2, _, body2, err2 = fetch(pub_url)
                time.sleep(delay)
                pubs = _json(body2) if body2 and not err2 else None
                if isinstance(pubs, dict):
                    pub_list = pubs.get("publications") or pubs.get("items") or []
                else:
                    pub_list = pubs or []
                for pub_item in pub_list:
                    for f in (pub_item.get("links") or []) + (pub_item.get("files") or []) + [pub_item]:
                        if not isinstance(f, dict):
                            continue
                        url = f.get("url") or f.get("fileUrl") or f.get("downloadUrl")
                        ctype = f"{f.get('contentType') or ''} {f.get('title') or ''}"
                        if url and (".pdf" in str(url).lower() or "pdf" in ctype.lower()):
                            add(url, f"{title} — {pub_item.get('title') or f.get('title')}")
            total = (data or {}).get("totalResults") or (data or {}).get("totalCount")
            skip += take
            if total is not None and skip >= int(total):
                break
            if len(items) < take:
                break

    # --- legislation.gov.uk feeds ---
    if "legislation.gov.uk" in host or "thegazette.co.uk" in host:
        for feed in (
            "https://www.legislation.gov.uk/new/data.feed",
            "https://www.legislation.gov.uk/uksi/data.feed",
            "https://www.legislation.gov.uk/ukpga/data.feed",
            "https://www.legislation.gov.uk/ukla/data.feed",
            "https://www.legislation.gov.uk/new/uksi/data.feed",
            "https://www.thegazette.co.uk/all-notices/notice/data.feed",
        ):
            st, _, body, err = fetch(feed)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(feed, html):
                u = link["url"].split("?")[0].rstrip("/")
                if link["is_pdf"]:
                    add(link["url"], link["text"])
                    continue
                # Document pages → /data.pdf
                if re.search(r"legislation\.gov\.uk/(ukpga|uksi|ukla|asp|anaw|nia|wsi|ssi)/", u):
                    # keep type/year/number
                    parts = u.replace("https://www.legislation.gov.uk/", "").split("/")
                    if len(parts) >= 3:
                        base = "https://www.legislation.gov.uk/" + "/".join(parts[:3])
                        add(base + "/data.pdf", link["text"] or base)
                        add(base + "/pdfs/contents.pdf", link["text"] or base)

    # --- US Federal Register (paginated; one site alone can exceed 300 PDFs) ---
    # Only attach the bulk FR API to federalregister.gov so ecfr/govinfo do not triple-count.
    if "federalregister.gov" in host:
        per_page = 100
        max_pages = 10  # up to 1000 newest FR docs with PDFs
        for page in range(1, max_pages + 1):
            api = (
                "https://www.federalregister.gov/api/v1/documents.json"
                f"?per_page={per_page}&page={page}&order=newest"
                "&conditions%5Btype%5D%5B%5D=RULE"
                "&conditions%5Btype%5D%5B%5D=PRORULE"
                "&conditions%5Btype%5D%5B%5D=NOTICE"
                "&conditions%5Btype%5D%5B%5D=PRESDOCU"
            )
            st, _, body, err = fetch(api)
            time.sleep(delay)
            data = _json(body) if body and not err and st and st < 400 else None
            results = (data or {}).get("results") or []
            if not results:
                break
            for doc in results:
                title = doc.get("title") or "Federal Register"
                if doc.get("pdf_url"):
                    add(doc["pdf_url"], title)
            total_pages = (data or {}).get("total_pages")
            if total_pages is not None and page >= int(total_pages):
                break
            if len(results) < per_page:
                break

    # Congress.gov / GovInfo listing pages
    if "congress.gov" in host or "govinfo.gov" in host:
        for u in (
            "https://www.congress.gov/search?q=%7B%22source%22%3A%22legislation%22%7D&pageSort=latestAction%3Adesc",
            "https://www.govinfo.gov/app/collection/bills",
            "https://www.govinfo.gov/app/collection/fr",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])

    # --- Canada openparliament + LEGISinfo HTML mirrors ---
    if "parl.ca" in host or "canada.ca" in host or "gazette.gc.ca" in host:
        for u in (
            "https://openparliament.ca/bills/",
            "https://www.parl.ca/legisinfo/en/bills/rss",
            "https://www.gazette.gc.ca/rp-pr/p2/index-eng.html",
            "https://www.gazette.gc.ca/rp-pr/p1/index-eng.html",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])
            # openparliament bill pages sometimes have PDF of bill text via parl.ca
            if "openparliament.ca/bills" in u:
                for link in extract_links(u, html)[:30]:
                    if "/bills/" in link["url"] and link["url"].count("/") >= 5:
                        st2, _, body2, err2 = fetch(link["url"])
                        time.sleep(delay)
                        if err2 or not body2:
                            continue
                        h2 = body2.decode("utf-8", errors="replace")
                        for p in extract_links(link["url"], h2):
                            if p["is_pdf"] or "pdf" in (p["text"] or "").lower():
                                add(p["url"], p["text"] or link["text"])

    # --- Spain BOE ---
    if "boe.es" in host or "congreso.es" in host:
        for u in (
            "https://www.boe.es/diario_boe/",
            "https://www.boe.es/buscar/legislacion.php",
            "https://www.congreso.es/es/proyectos-de-ley",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or "/pdf" in link["url"].lower() or "pdf" in (link["text"] or "").lower():
                    add(link["url"], link["text"])

    # --- Germany ---
    if "bundestag.de" in host or "gesetze-im-internet.de" in host or "recht.bund.de" in host:
        for u in (
            "https://www.bundestag.de/services/opendata",
            "https://dip.bundestag.de",
            "https://www.gesetze-im-internet.de/",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"]:
                    add(link["url"], link["text"])

    # --- France Legifrance / Assemblee ---
    if "legifrance.gouv.fr" in host or "assemblee-nationale.fr" in host:
        for u in (
            "https://www.legifrance.gouv.fr/jorf/jo",
            "https://www.assemblee-nationale.fr/dyn/16/textes",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])

    # --- NZ legislation ---
    if "legislation.govt.nz" in host or "parliament.nz" in host or "gazette.govt.nz" in host:
        for u in (
            "https://www.legislation.govt.nz/subscribe/atom.aspx?subscriptiontype=0&subscriptionid=0",
            "https://www.legislation.govt.nz/bill/government/recent.aspx",
            "https://gazette.govt.nz/home/NoticeSearch?noticeType=go",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])
                # NZ acts often have PDF via /whole.html → pdf link patterns
                if "/act/" in link["url"] or "/bill/" in link["url"]:
                    add(link["url"].replace("/whole.html", "") + "/latest/whole.pdf", link["text"])

    # --- Australia Federal Register of Legislation ---
    if "legislation.gov.au" in host or "aph.gov.au" in host:
        for u in (
            "https://www.legislation.gov.au/WhatsNew",
            "https://www.legislation.gov.au/Browse/Results/ByPublicationDate/Acts/Asmade/0/0/All/Principal",
            "https://www.aph.gov.au/Parliamentary_Business/Bills_Legislation/Bills_Search_Results/Result?bId=r",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or "Download" in (link["text"] or "") or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])

    # --- India PRS already works via HTML; also try sansad ---
    if "prsindia.org" in host or "egazette" in host or "sansad.in" in host:
        for u in (
            "https://prsindia.org/billtrack",
            "https://prsindia.org/billtrack/filter/recent",
            "https://sansad.in/ls/legislation/bills",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])

    # --- Japan e-Gov / House ---
    if "e-gov.go.jp" in host or "shugiin.go.jp" in host or "sangiin.go.jp" in host or "kanpou" in host:
        for u in (
            "https://www.e-gov.go.jp/",
            "https://www.shugiin.go.jp/internet/itdb_gian.nsf/html/gian/menu.htm",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"]:
                    add(link["url"], link["text"])

    # --- Brazil ---
    if "planalto.gov.br" in host or "camara.leg.br" in host or "in.gov.br" in host:
        for u in (
            "https://www.in.gov.br/leiturajornal",
            "https://www.camara.leg.br/proposicoesWeb/prop_lista?sigla=PL&tipoAutor=todos",
            "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/lei/",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])

    # --- Ireland ---
    if "oireachtas.ie" in host or "irisoifigiuil.ie" in host or "irishstatutebook.ie" in host:
        for u in (
            "https://www.oireachtas.ie/en/bills/",
            "https://www.irishstatutebook.ie/eli/isbc/recent.html",
            "https://www.irisoifigiuil.ie/",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])

    # --- Singapore ---
    if "parliament.gov.sg" in host or "sso.agc.gov.sg" in host:
        for u in (
            "https://www.parliament.gov.sg/parliamentary-business/bills-introduced",
            "https://sso.agc.gov.sg/Browse/Act/Current",
            "https://sso.agc.gov.sg/Browse/SL/Current",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or looks_like_bill(link["url"], link["text"]):
                    add(link["url"], link["text"])

    # --- EUR-Lex ---
    if "eur-lex.europa.eu" in host or "europarl.europa.eu" in host:
        for u in (
            "https://eur-lex.europa.eu/oj/direct-access.html",
            "https://eur-lex.europa.eu/search.html?scope=EURLEX&type=quick&lang=en&DTS_DOM=EU_LAW&qid=",
        ):
            st, _, body, err = fetch(u)
            time.sleep(delay)
            if err or not body or (st and st >= 400):
                continue
            html = body.decode("utf-8", errors="replace")
            for link in extract_links(u, html):
                if link["is_pdf"] or "PDF" in (link["text"] or "").upper():
                    add(link["url"], link["text"])

    # de-dupe
    seen = set()
    uniq = []
    for x in out:
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        uniq.append(x)
    return uniq

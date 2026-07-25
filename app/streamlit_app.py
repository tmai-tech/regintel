"""Local Streamlit UI for BCI RegIntel (optional; primary UI is GitHub Pages)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
if not (DATA / "primary_sources.json").exists():
    DATA = ROOT / "web" / "data"


def load(name: str):
    path = DATA / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


st.set_page_config(page_title="BCI RegIntel", layout="wide", page_icon="⚖️")
st.title("BCI Regulatory Intelligence")
st.caption("Legal act & regulatory update tracking — source catalog, tracking log, collector updates")

meta = load("meta.json")
if meta:
    c1, c2, c3, c4, c5 = st.columns(5)
    counts = meta.get("counts", {})
    c1.metric("Primary sources", counts.get("primary_sources", 0))
    c2.metric("Tracking records", counts.get("tracking_records", 0))
    c3.metric("Gazette sources", counts.get("gazette_sources", 0))
    c4.metric("Secondary", counts.get("secondary_sources", 0))
    c5.metric("Collector updates", counts.get("updates", 0))
    if meta.get("last_collector_run"):
        st.info(f"Last collector run: {meta['last_collector_run']} — {meta.get('last_collector_stats')}")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Tracking log", "Primary sources", "Collector updates", "Gazette", "Secondary"]
)

with tab1:
    df = pd.DataFrame(load("tracking.json"))
    if not df.empty:
        cols = st.columns(4)
        countries = ["All"] + sorted(df["country"].dropna().unique().tolist()) if "country" in df else ["All"]
        areas = ["All"] + sorted(df["law_area"].dropna().unique().tolist()) if "law_area" in df else ["All"]
        rel = ["All"] + sorted(df["relevancy"].dropna().unique().tolist()) if "relevancy" in df else ["All"]
        country = cols[0].selectbox("Country", countries)
        area = cols[1].selectbox("Law area", areas)
        relevancy = cols[2].selectbox("Relevancy", rel)
        q = cols[3].text_input("Search remarks/topic")
        view = df.copy()
        if country != "All":
            view = view[view["country"] == country]
        if area != "All":
            view = view[view["law_area"] == area]
        if relevancy != "All":
            view = view[view["relevancy"] == relevancy]
        if q:
            mask = view.astype(str).apply(lambda r: q.lower() in " ".join(r.values).lower(), axis=1)
            view = view[mask]
        st.dataframe(view, use_container_width=True, height=520)
        st.download_button("Download CSV", view.to_csv(index=False), "tracking.csv", "text/csv")
    else:
        st.warning("No tracking data")

with tab2:
    df = pd.DataFrame(load("primary_sources.json"))
    if not df.empty:
        if "topics" in df.columns:
            df = df.copy()
            df["topics"] = df["topics"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
        cols = st.columns(4)
        regions = ["All"] + sorted(df["region"].dropna().unique().tolist())
        region = cols[0].selectbox("Region", regions, key="pr")
        juris = ["All"] + sorted(df["jurisdiction"].dropna().unique().tolist())
        jurisdiction = cols[1].selectbox("Jurisdiction", juris, key="pj")
        status = cols[2].selectbox("Status", ["All"] + sorted(df["status"].dropna().unique().tolist()), key="ps")
        q = cols[3].text_input("Search authority/URL", key="pq")
        view = df.copy()
        if region != "All":
            view = view[view["region"] == region]
        if jurisdiction != "All":
            view = view[view["jurisdiction"] == jurisdiction]
        if status != "All":
            view = view[view["status"] == status]
        if q:
            mask = view.astype(str).apply(lambda r: q.lower() in " ".join(r.values).lower(), axis=1)
            view = view[mask]
        st.dataframe(view, use_container_width=True, height=520)
    else:
        st.warning("No primary sources")

with tab3:
    df = pd.DataFrame(load("updates.json"))
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=520)
    else:
        st.info("No collector updates yet. Run: python collector/run_daily.py")

with tab4:
    st.dataframe(pd.DataFrame(load("gazette.json")), use_container_width=True, height=520)

with tab5:
    st.dataframe(pd.DataFrame(load("secondary_sources.json")), use_container_width=True, height=520)

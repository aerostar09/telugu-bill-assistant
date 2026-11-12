"""DISCOM tab: real public-complaint counts + clearly labelled sample illustrations."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

COMPLAINTS_CSV = Path(__file__).resolve().parent / "data" / "complaints_public.csv"
SOURCE_LABEL = "public posts/news, n=71"

# Telangana's 33 districts with approximate HQ coordinates (public knowledge).
# Values on the map are ILLUSTRATIVE sample intensities, not live DISCOM data.
TG_DISTRICT_HQ = [
    ("Adilabad", 19.6641, 78.5320),
    ("Bhadradri Kothagudem", 17.5511, 80.6197),
    ("Hanumakonda", 18.0072, 79.5581),
    ("Hyderabad", 17.3850, 78.4867),
    ("Jagtial", 18.7948, 78.9164),
    ("Jangaon", 17.7260, 79.1820),
    ("Jayashankar Bhupalpally", 18.4360, 79.8640),
    ("Jogulamba Gadwal", 16.2340, 77.8000),
    ("Kamareddy", 18.3200, 78.3410),
    ("Karimnagar", 18.4386, 79.1288),
    ("Khammam", 17.2473, 80.1514),
    ("Kumuram Bheem", 19.3640, 79.4740),
    ("Mahabubabad", 17.5980, 80.0020),
    ("Mahabubnagar", 16.7484, 77.9860),
    ("Mancherial", 18.8720, 79.4440),
    ("Medak", 18.0450, 78.2610),
    ("Medchal-Malkajgiri", 17.5430, 78.4830),
    ("Mulugu", 18.1910, 80.0080),
    ("Nagarkurnool", 16.4850, 78.3100),
    ("Nalgonda", 17.0570, 79.2670),
    ("Narayanpet", 16.7450, 77.4960),
    ("Nirmal", 19.0960, 78.3440),
    ("Nizamabad", 18.6725, 78.0941),
    ("Peddapalli", 18.6160, 79.3830),
    ("Rajanna Sircilla", 18.3890, 78.8100),
    ("Rangareddy", 17.2540, 78.3570),
    ("Sangareddy", 17.6290, 78.0860),
    ("Siddipet", 18.1010, 78.8520),
    ("Suryapet", 17.1400, 79.6200),
    ("Vikarabad", 17.3380, 77.9040),
    ("Wanaparthy", 16.3650, 78.0620),
    ("Warangal", 17.9689, 79.5941),
    ("Yadadri Bhuvanagiri", 17.5100, 78.8880),
]


def load_complaints(path: Optional[Path] = None) -> List[Dict[str, str]]:
    p = path or COMPLAINTS_CSV
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def issue_counts(rows: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    rows = rows if rows is not None else load_complaints()
    c = Counter((r.get("specific_issue") or "unspecified") for r in rows)
    return [{"specific_issue": k, "count": int(v)} for k, v in c.most_common()]


def sample_map_rows() -> List[Dict[str, Any]]:
    """Deterministic illustrative intensities (1–10). Not live complaints."""
    out = []
    for i, (name, lat, lon) in enumerate(TG_DISTRICT_HQ):
        intensity = 1 + (sum(ord(ch) for ch in name) + i * 3) % 10
        out.append({"district": name, "lat": lat, "lon": lon, "sample_intensity": intensity})
    return out


def sample_anomaly_rows() -> List[Dict[str, Any]]:
    """Fake masked service numbers. Labelled sample — not real consumers."""
    return [
        {"service_no": "XXXX1234", "prev_units": 150, "curr_units": 650, "ratio": 4.33, "flag": "usage jump >2.5×", "status": "sample"},
        {"service_no": "XXXX5610", "prev_units": 90, "curr_units": 310, "ratio": 3.44, "flag": "usage jump >2.5×", "status": "sample"},
        {"service_no": "XXXX8821", "prev_units": 210, "curr_units": 205, "ratio": 0.98, "flag": "none", "status": "sample"},
        {"service_no": "XXXX4402", "prev_units": 40, "curr_units": 180, "ratio": 4.50, "flag": "usage jump >2.5×", "status": "sample"},
        {"service_no": "XXXX7099", "prev_units": 120, "curr_units": 126, "ratio": 1.05, "flag": "none", "status": "sample"},
        {"service_no": "XXXX3378", "prev_units": 80, "curr_units": 260, "ratio": 3.25, "flag": "usage jump >2.5×", "status": "sample"},
    ]


def queries_avoided_concept(rows: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Concept illustration only — not a measured DISCOM KPI or official percentage."""
    rows = rows if rows is not None else load_complaints()
    n = len(rows)
    yes = sum(1 for r in rows if (r.get("would_our_app_answer") or "").strip().lower() == "yes")
    partial = sum(1 for r in rows if (r.get("would_our_app_answer") or "").strip().lower() == "partial")
    return {
        "n": n,
        "yes": yes,
        "partial": partial,
        "source_label": SOURCE_LABEL,
        "note": (
            "Concept illustration (sample, not a measured impact statistic): "
            f"in this public set of {n} posts, {yes} look fully explainable by a bill assistant "
            f"and {partial} look partially explainable. That is a 'queries that might have been "
            "avoided' idea — not an official 1912 deflection rate."
        ),
    }


def render_discom_dashboard() -> None:
    import pandas as pd
    import streamlit as st

    st.subheader("DISCOM dashboard")
    st.caption(
        "Bar chart uses real counts from an anonymised public-complaint set "
        f"({SOURCE_LABEL}). The map, anomaly table and queries-avoided counter are "
        "labelled SAMPLE / illustrative — not live or official DISCOM data."
    )

    rows = load_complaints()
    counts = issue_counts(rows)
    st.markdown("##### Public complaint themes")
    st.caption(f"Source: {SOURCE_LABEL}. Handles, URLs and quotes removed.")
    cdf = pd.DataFrame(counts)
    st.bar_chart(cdf, x="specific_issue", y="count", horizontal=True, height=480)
    st.dataframe(cdf, hide_index=True, width="stretch")

    st.markdown("##### Telangana district map")
    st.warning("SAMPLE DATA (illustrative) — not live DISCOM complaints, not real-time.")
    try:
        import plotly.express as px
        mdf = pd.DataFrame(sample_map_rows())
        fig = px.scatter_geo(
            mdf,
            lat="lat",
            lon="lon",
            size="sample_intensity",
            color="sample_intensity",
            hover_name="district",
            projection="natural earth",
            title="SAMPLE DATA (illustrative) — Telangana districts",
        )
        fig.update_geos(
            visible=True,
            resolution=50,
            showcountries=True,
            showsubunits=True,
            lataxis_range=[15.5, 20.3],
            lonaxis_range=[76.7, 81.4],
            bgcolor="#f7faf9",
        )
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=480, coloraxis_colorbar_title="sample")
        st.plotly_chart(fig, width="stretch")
        with st.expander("Sample intensity table"):
            st.dataframe(mdf[["district", "sample_intensity"]], hide_index=True, width="stretch")
    except Exception as e:
        st.info("Map could not be drawn in this environment; sample table is below.")
        st.caption(str(e))
        st.dataframe(pd.DataFrame(sample_map_rows()), hide_index=True, width="stretch")

    st.markdown("##### Flagged-anomaly table")
    st.caption("SAMPLE — fake masked service numbers (e.g. XXXX1234). Not real consumers.")
    adf = pd.DataFrame(sample_anomaly_rows())
    flags = ["all"] + sorted(set(adf["flag"].tolist()))
    choice = st.selectbox("Filter flag", flags, key="discom_flag_filter")
    shown = adf if choice == "all" else adf[adf["flag"] == choice]
    st.dataframe(shown, hide_index=True, width="stretch")

    concept = queries_avoided_concept(rows)
    st.markdown("##### 'Queries avoided' — concept counter")
    st.info(concept["note"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Public posts in set", concept["n"])
    c2.metric("Would our app answer? yes", concept["yes"])
    c3.metric("partial", concept["partial"])
    st.caption("These counts are from the public set only. No invented percentage is presented as a real KPI.")

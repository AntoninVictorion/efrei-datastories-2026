"""Cancers and dementia in France (2015-2024): Streamlit app.

Run from the project root: streamlit run app.py
Data: tables built by scripts/prep.py (data/processed/*.parquet).
"""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.viz import trend_chart, index_map, region_chart, OVERSEAS

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
SEX_LABELS = {"T": "All", "H": "Men", "F": "Women"}
SEX_COLORS = {"T": "#1f4e79", "H": "#1f77b4", "F": "#d95f02"}

st.set_page_config(page_title="Cancers and dementia in France", page_icon="📈", layout="wide")


@st.cache_data(show_spinner=False)
def load(name):
    return pd.read_parquet(PROC / f"{name}.parquet")


@st.cache_data
def load_geojson():
    with open(ROOT / "data" / "geo" / "departements.geojson", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def dept_names():
    """Department code -> name (the data only has codes)."""
    names = {x["properties"]["code"]: x["properties"]["nom"] for x in load_geojson()["features"]}
    names.update({"971": "Guadeloupe", "972": "Martinique", "973": "Guyane",
                  "974": "La Réunion", "976": "Mayotte"})
    return names

def fmt(x, digits=0, suffix=""):
    """Format a number for display, 'n/a' when missing."""
    return "n/a" if pd.isna(x) else f"{x:,.{digits}f}{suffix}"


# --- Load data
tables = ("trend_national", "profile_age_sex", "index_territoire")
if any(not (PROC / f"{t}.parquet").exists() for t in tables):
    st.error("Missing tables in data/processed: run `python scripts/prep.py` first.")
    st.stop()
trend, profile, index = (load(t) for t in tables)
departments = dept_names()

# --- Header
st.title("Cancers and dementia in France: a changing prevalence")
st.caption("Source: French National Health Insurance (CNAM), 'Pathologies: number of patients by condition, "
           "sex, age group and territory' (data.gouv.fr, ODbL licence), 2015-2024.")

# --- Sidebar filters
with st.sidebar:
    st.header("Filters")
    options = (trend[trend["niveau"].isin(["categorie", "type"])]
               [["top", "label", "famille", "niveau"]].drop_duplicates()
               .sort_values(["famille", "niveau", "label"]))
    names = {r.top: (f"{r.label} (all)" if r.niveau == "categorie" else r.label)
             for r in options.itertuples()}
    top = st.selectbox("Condition", list(names), format_func=names.get,
                       help="'(all)' groups every type in the family.")
    available = set(trend.loc[trend["top"] == top, "sexe"])
    sexe = st.radio("Sex", [s for s in SEX_LABELS if s in available], format_func=SEX_LABELS.get)
    years = sorted(int(y) for y in trend["annee"].unique())
    y0, y1 = st.slider("Period", years[0], years[-1], (years[0], years[-1]))
    codes = sorted(departments, key=departments.get)
    dept = st.selectbox("Department", codes, index=codes.index("59"),
                        format_func=lambda c: f"{departments[c]} ({c})")

# France series for the selected condition, sex and period
win = trend[(trend["top"] == top) & (trend["sexe"] == sexe)
            & trend["annee"].between(y0, y1)].sort_values("annee")
if win.empty:
    st.warning("No data for this selection.")
    st.stop()
first, last = win.iloc[0], win.iloc[-1]
label = names[top]

# --- Key figures (France)
c1, c2, c3 = st.columns(3)
delta = None
if y1 > y0 and pd.notna(first["prevalence"]) and pd.notna(last["prevalence"]):
    delta = f"{last['prevalence'] - first['prevalence']:+.2f} pt since {y0}"
c1.metric(f"Prevalence in {y1}", fmt(last["prevalence"], 2, "%"), delta,
          help="Share of insured people treated for this condition.")
c2.metric(f"Patients in {y1}", fmt(last["effectif"]), help="Published counts, rounded to the nearest 10.")
c3.metric("Reference population", fmt(last["population"]),
          help="Insured people who used healthcare during the year, not the whole population.")

# --- Trend: selected department vs France
st.subheader(f"{label}: how has it changed since {y0}?")
dept_df = index[(index["geo_level"] == "dept") & (index["top"] == top)
                & (index["sexe"] == sexe) & (index["dept"] == dept)]
dept_df = dept_df[dept_df["annee"].between(y0, y1)].sort_values("annee")
dept_df = dept_df.rename(columns={"prevalence_brute": "prevalence"})

fig = trend_chart(win, dept_df, departments[dept], f"{label}: change since {y0}")
if top == "NEU_DEM_CAT" and y0 <= 2018 <= y1:   # dementia only: possible break
    fig.add_vline(x=2018, line_dash="dot",
                  annotation_text="Aug 2018: drug reimbursement ended (possible break)")
st.plotly_chart(fig)
st.caption(f"Chart description: prevalence of {label} for {departments[dept]} compared "
           f"with France, rebased to 100 in {y0}.")

# --- Map: comparative index by department
st.subheader(f"Where is {label} above what age explains? ({y1})")
idx = index[(index["geo_level"] == "dept") & (index["top"] == top)
            & (index["sexe"] == sexe) & (index["annee"] == y1)]
st.plotly_chart(index_map(idx, load_geojson(), departments, f"Comparative index, {y1}"))

st.caption("Overseas departments (off the map):")
for col, code in zip(st.columns(5), OVERSEAS):
    value = idx.loc[idx["dept"] == code, "indice"]
    col.metric(departments[code], fmt(value.iloc[0], 2) if len(value) else "n/a")

st.caption("Index = observed cases / cases expected from the age structure (1.2 = 20% more than expected). "
           "Grey: within +/-10% of France. Colours are capped at 0.7-1.3. "
           "A statistical gap, not a causal explanation.")

# --- Regions: where to look first
st.subheader(f"Which regions should we look at first? ({y1})")
reg = index[(index["geo_level"] == "region") & (index["top"] == top)
            & (index["sexe"] == sexe) & (index["annee"] == y1)].dropna(subset=["indice"])
st.plotly_chart(region_chart(reg, f"Comparative index by region, {y1}"))
st.caption("Grey band: within +/-10% of France. Grey bars: 95% confidence interval. "
           "Values below 0.6 are off the chart (e.g. Mayotte). A gap shows where to look, not why.")

# --- Prevalence by age (France)
st.subheader(f"Prevalence by age group in {y1}")
prof = profile[(profile["top"] == top) & (profile["annee"] == y1)].copy()
prof["age_label"] = prof["age_label"].str.replace(" ans et +", "+").str.replace(" ans", "")
order = prof.drop_duplicates("age_label").sort_values("age_min")["age_label"].tolist()

fig2 = go.Figure()
for s in [s for s in ("H", "F") if s in set(prof["sexe"])] or ["T"]:
    p = prof[prof["sexe"] == s].sort_values("age_min")
    fig2.add_scatter(x=p["age_label"], y=p["prevalence"], name=SEX_LABELS[s], mode="lines+markers",
                     line=dict(color=SEX_COLORS[s], width=3))
fig2.update_layout(template="plotly_white", xaxis_title="Age group (years)",
                   yaxis_title="Prevalence (%)", xaxis=dict(categoryorder="array", categoryarray=order))
st.plotly_chart(fig2)
st.caption("Age groups with fewer than 11 patients are hidden (statistical confidentiality): "
           "the curve may be cut for the youngest ages.")

with st.expander("How to read these figures"):
    st.markdown(
        "- **Prevalence**: share of insured people treated for the condition, detected from reimbursed care "
        "(CNAM algorithms). It is not a clinical diagnosis.\n"
        "- **Counts** are rounded to the nearest 10; counts below 11 are hidden.\n"
        "- **Not age-standardised** (France curve): a rise can reflect population ageing.\n"
        "- **2020**: lower use of healthcare during Covid-19 may have reduced detected cases.")
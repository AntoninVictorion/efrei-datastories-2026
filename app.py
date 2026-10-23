"""Cancers and dementia in France (2015-2024): Streamlit app.

Run from the project root: streamlit run app.py
Story: 1 paradox, 2 age, 3 one department, 4 map, 5 regions, 6 gap over time, 7 priorities,
8 takeaways, then data quality.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from sections.quality import show_quality
from utils import story
from utils.labels import CONDITION_NAMES, SEX_LABELS, SHORT_NAMES
from utils.viz import (OVERSEAS, age_chart, gap_chart, index_map, priority_chart,
                       region_chart, trend_chart, with_excess)

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
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


def fmt(x, digits=0, suffix="", sign=False):
    """Format a number for display, 'n/a' when missing."""
    return "n/a" if pd.isna(x) else f"{x:{'+' if sign else ''},.{digits}f}{suffix}"


def pct_change(a, b):
    """Relative change from a to b, in %."""
    return (b / a - 1) * 100


# --- Load data
tables = ("trend_national", "profile_age_sex", "index_territoire")
if any(not (PROC / f"{t}.parquet").exists() for t in tables):
    st.error("Missing tables in data/processed: run `python scripts/prep.py` first.")
    st.stop()
trend, profile, index = (load(t) for t in tables)
departments = dept_names()
years = sorted(int(y) for y in trend["annee"].unique())

# --- Sidebar filters (they apply from section 3 onwards)
with st.sidebar:
    st.header("Filters")
    st.caption("Sections 1 and 2 are national and do not change. The filters apply from section 3.")
    names = {t: n for t, n in CONDITION_NAMES.items() if t in set(trend["top"])}
    top = st.selectbox("Condition", list(names), index=list(names).index("NEU_DEM_CAT"),
                       format_func=names.get)
    available = set(trend.loc[trend["top"] == top, "sexe"])
    sexe = st.radio("Sex", [s for s in SEX_LABELS if s in available], format_func=SEX_LABELS.get)
    y0, y1 = st.slider("Period", years[0], years[-1], (years[0], years[-1]),
                       help="The end year is also the year shown on the map and in the charts below.")
    codes = sorted(departments, key=departments.get)
    dept = st.selectbox("Department", codes, index=codes.index("59"),
                        format_func=lambda c: f"{departments[c]} ({c})")
label = names[top]

# --- Header
st.title("Cancers and dementia in France: where does the burden exceed what age explains?")
st.caption("Source: French National Health Insurance (CNAM), 'Pathologies: number of patients by condition, "
           "sex, age group and territory' (data.gouv.fr, ODbL licence), 2015-2024.")

# --- 1. Hook: the paradox (national, all sexes)
st.header("1. A paradox: cancer up, dementia down")
national = trend[trend["sexe"] == "T"]
cancers = national[national["top"] == "CAN_CAT_CAT"].sort_values("annee")
dementia = national[national["top"] == "NEU_DEM_CAT"].sort_values("annee")
st.markdown(story.hook_text(years[0], years[-1],
                            pct_change(cancers["prevalence"].iloc[0], cancers["prevalence"].iloc[-1]),
                            pct_change(dementia["prevalence"].iloc[0], dementia["prevalence"].iloc[-1])))
fig = trend_chart(cancers, dementia, "Dementia", "France: cancers vs dementia (all sexes)", france_name="Cancers")
fig.add_vline(x=2018, line_dash="dot",
              annotation_text="Aug 2018: dementia drug reimbursement ended (possible break)")
st.plotly_chart(fig)
st.caption("Chart description: national prevalence of cancers and of dementia, each rebased to 100 in 2015.")

# --- 2. Context: why raw numbers mislead
st.header("2. Why raw numbers mislead: age")
st.markdown(story.AGE_TEXT)
age_df = profile[profile["top"].isin(SHORT_NAMES) & (profile["annee"] == years[-1])
                 & profile["sexe"].isin(["H", "F"])].copy()
age_df["condition"] = age_df["top"].map(SHORT_NAMES)
age_df["sex"] = age_df["sexe"].map(SEX_LABELS)
st.plotly_chart(age_chart(age_df.sort_values("age_mid"), f"Prevalence by age, France, {years[-1]}"))
st.caption("Each panel has its own scale: compare the shapes, not the levels. "
           "Age groups with fewer than 11 patients are hidden (statistical confidentiality).")

# --- 3. One department: raw prevalence vs age-adjusted index
st.header(f"3. {departments[dept]}: raw prevalence vs age-adjusted index")
win = trend[(trend["top"] == top) & (trend["sexe"] == sexe)
            & trend["annee"].between(y0, y1)].sort_values("annee")
dept_df = index[(index["geo_level"] == "dept") & (index["top"] == top)
                & (index["sexe"] == sexe) & (index["dept"] == dept)]
dept_df = dept_df[dept_df["annee"].between(y0, y1)].sort_values("annee")
dept_df = dept_df.rename(columns={"prevalence_brute": "prevalence"})
if win.empty or dept_df.empty:
    st.warning("No data for this selection.")
    st.stop()
first, last = win.iloc[0], win.iloc[-1]
d_first, d_last = dept_df.iloc[0], dept_df.iloc[-1]

gap = pct_change(last["prevalence"], d_last["prevalence"])               # department vs France
change_dept = pct_change(d_first["prevalence"], d_last["prevalence"])
change_france = pct_change(first["prevalence"], last["prevalence"])
share = d_last["effectif_observe"] / last["effectif"] * 100               # share of French patients

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Prevalence in {y1}", fmt(d_last["prevalence"], 2, "%"),
          f"{fmt(gap, 0, '%', True)} vs France", delta_color="off",
          help="Share of insured people treated. Not adjusted for age: see the index.")
c2.metric(f"Change since {y0}", fmt(change_dept, 1, "%", True),
          f"{fmt(change_dept - change_france, 1, ' pts', True)} vs France", delta_color="off",
          help="Relative change of the prevalence over the selected period.")
c3.metric(f"Comparative index in {y1}", fmt(d_last["indice"], 2),
          help="Observed / expected cases given the age structure. 1.2 = 20% more than expected. "
               "Already relative to France (1 = France).")
c4.metric(f"Patients in {y1}", fmt(d_last["effectif_observe"]),
          f"{fmt(share, 1, '%')} of French patients", delta_color="off",
          help="Published counts, rounded to the nearest 10.")
st.markdown(story.kpi_text(departments[dept], gap, d_last["indice"]))

fig = trend_chart(win, dept_df, departments[dept], f"{label}: change since {y0}")
if top == "NEU_DEM_CAT" and y0 <= 2018 <= y1:   # dementia only: possible break
    fig.add_vline(x=2018, line_dash="dot",
                  annotation_text="Aug 2018: drug reimbursement ended (possible break)")
st.plotly_chart(fig)
st.caption(f"Chart description: prevalence of {label} for {departments[dept]} compared "
           f"with France, rebased to 100 in {y0}.")

# --- 4. Map: where?
st.header(f"4. Where is {label} above what age explains?")
idx = index[(index["geo_level"] == "dept") & (index["top"] == top)
            & (index["sexe"] == sexe) & (index["annee"] == y1)]
st.markdown(story.map_text(idx[~idx["dept"].isin(OVERSEAS)], departments))
st.plotly_chart(index_map(idx, load_geojson(), departments, f"Comparative index, {y1}"))

st.caption("Overseas departments (off the map):")
for col, code in zip(st.columns(5), OVERSEAS):
    value = idx.loc[idx["dept"] == code, "indice"]
    col.metric(departments[code], fmt(value.iloc[0], 2) if len(value) else "n/a")
st.caption("Index = observed cases / cases expected from the age structure (1.2 = 20% more than expected). "
           "Grey: within +/-10% of France. Colours are capped at 0.7-1.3. "
           "A statistical gap, not a causal explanation.")

# --- 5. Regions: which ones, and how sure are we?
st.header(f"5. Which regions stand out? ({y1})")
reg = index[(index["geo_level"] == "region") & (index["top"] == top)
            & (index["sexe"] == sexe) & (index["annee"] == y1)].dropna(subset=["indice"])
st.markdown(story.region_text(reg))
st.plotly_chart(region_chart(reg, f"Comparative index by region, {y1}"))
st.caption("Grey band: within +/-10% of France. Grey bars: 95% confidence interval. "
           "Values below 0.6 are off the chart (e.g. Mayotte). A gap shows where to look, not why.")

# --- 6. Is the gap changing?
st.header("6. Are the gaps growing or shrinking?")
if y0 == y1:
    st.info("Select a period of at least two years in the sidebar to see how the gaps evolve.")
else:
    reg2 = index[(index["geo_level"] == "region") & (index["top"] == top)
                 & (index["sexe"] == sexe) & index["annee"].isin([y0, y1])]
    st.markdown(story.gap_text(reg2.dropna(subset=["indice"]), y0, y1))
    st.plotly_chart(gap_chart(reg2, y0, y1, f"Comparative index by region, {y0} vs {y1}"))
    st.caption("Each segment links a region's index in the first and the last year. "
               "A shorter distance to 1 means the region is closer to what its age structure predicts.")

# --- 7. Priorities: intensity vs volume
st.header("7. Where should we look first? Intensity vs volume")
prio = with_excess(idx.dropna(subset=["indice", "effectif_observe"]))
st.markdown(story.priority_text(prio, departments))
st.plotly_chart(priority_chart(prio, departments, f"{label}: index vs patients above expected, {y1}"))
st.caption("A small department can have a high index but few extra patients, while a large one with a modest "
           "index can have many. Both criteria matter. Counts are rounded to 10.")

# --- 8. Takeaways
st.header("8. Key takeaways and next steps")
st.markdown(
    "1. **Raw prevalence mixes disease burden and age.** Compare territories with the comparative index, "
    "not with raw prevalence.\n"
    "2. **Look first where the index is more than 10% above expected *and* the number of extra patients is large.** "
    "The map shows where, the dot plot how sure we are, the last chart how many patients are concerned.\n"
    "3. **A gap is a place to investigate, not a diagnosis of need.** It can reflect detection, "
    "access to care or coding practices as much as real burden.\n\n"
    "**Next steps:** check local screening and memory-clinic access in the flagged territories, verify the possible "
    "2018 break in the dementia series with the CNAM method note, and extend the index to rates standardised "
    "on a common age structure.")

# --- Data quality and limitations
st.divider()
if (PROC / "quality_report.json").exists():
    show_quality(json.loads((PROC / "quality_report.json").read_text(encoding="utf-8")))
else:
    st.warning("quality_report.json not found: run `python scripts/build_facts.py`.")
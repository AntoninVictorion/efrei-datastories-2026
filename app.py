"""Cancers et démences en France (2015-2024) : application Streamlit, version 1.

Contenu : filtres latéraux, indicateurs clés, tendance nationale, profil par âge.
Lancer depuis la racine du projet : streamlit run app.py
Données : tables produites par scripts/prep.py (data/processed/*.parquet).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
SEXE_LABELS = {"T": "Tous sexes", "H": "Hommes", "F": "Femmes"}
SEXE_COLORS = {"T": "#1f4e79", "H": "#1f77b4", "F": "#d95f02"}   # contrastés, distinguables sans la couleur seule

st.set_page_config(page_title="Cancers et démences en France", page_icon="📈", layout="wide")


@st.cache_data(show_spinner=False)
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(PROC / f"{name}.parquet")


def fmt_int(x) -> str:
    return "n.d." if pd.isna(x) else f"{int(x):,}".replace(",", " ")


def fmt_pct(x, digits: int = 2) -> str:
    return "n.d." if pd.isna(x) else f"{x:.{digits}f} %"


missing = [n for n in ("trend_national", "profile_age_sex") if not (PROC / f"{n}.parquet").exists()]
if missing:
    st.error("Tables introuvables dans data/processed : lancer d'abord `python scripts/prep.py`.")
    st.stop()

trend = load("trend_national")
profile = load("profile_age_sex")

# --------------------------------------------------------------------------- #
# En-tête
# --------------------------------------------------------------------------- #
st.title("Cancers et démences en France : une prévalence qui évolue")
st.caption("Source : Caisse nationale de l'Assurance Maladie, « Pathologies : effectif de patients par pathologie, "
           "sexe, classe d'âge et territoire » (data.gouv.fr, licence ODbL), 2015-2024.")

# --------------------------------------------------------------------------- #
# Filtres
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Filtres")
    options = (trend[trend["niveau"].isin(["categorie", "type"])]
               [["top", "label", "famille", "niveau"]].drop_duplicates()
               .sort_values(["famille", "niveau", "label"]))
    names = {r.top: (f"{r.label} (ensemble)" if r.niveau == "categorie" else r.label)
             for r in options.itertuples()}
    top = st.selectbox("Pathologie", list(names), format_func=names.get,
                       help="« Ensemble » regroupe tous les types de la famille.")
    available = set(trend.loc[trend["top"] == top, "sexe"])
    sexe = st.radio("Sexe", [s for s in SEXE_LABELS if s in available], format_func=SEXE_LABELS.get)
    years = sorted(int(y) for y in trend["annee"].unique())
    y0, y1 = st.slider("Période", years[0], years[-1], (years[0], years[-1]))

sub = trend[(trend["top"] == top) & (trend["sexe"] == sexe)].sort_values("annee")
win = sub[(sub["annee"] >= y0) & (sub["annee"] <= y1)]
if win.empty:
    st.warning("Aucune donnée pour cette sélection.")
    st.stop()
first, last = win.iloc[0], win.iloc[-1]
label = names[top]

# --------------------------------------------------------------------------- #
# Indicateurs clés
# --------------------------------------------------------------------------- #
c1, c2, c3 = st.columns(3)
delta = None
if y1 > y0 and pd.notna(first["prevalence"]) and pd.notna(last["prevalence"]):
    delta = f"{last['prevalence'] - first['prevalence']:+.2f} pt depuis {y0}"
c1.metric(f"Prévalence en {y1}", fmt_pct(last["prevalence"]), delta,
          help="Part des bénéficiaires de la cartographie pris en charge pour cette pathologie.")
c2.metric(f"Patients pris en charge en {y1}", fmt_int(last["effectif"]),
          help="Effectifs publiés, arrondis à la dizaine.")
c3.metric("Population de référence", fmt_int(last["population"]),
          help="Bénéficiaires de l'Assurance Maladie ayant eu recours aux soins dans l'année "
               "(population de la cartographie), et non la population totale.")

# --------------------------------------------------------------------------- #
# Tendance nationale
# --------------------------------------------------------------------------- #
if y1 > y0 and pd.notna(first["prevalence"]) and first["prevalence"] > 0 and pd.notna(last["prevalence"]):
    rel = (last["prevalence"] / first["prevalence"] - 1) * 100
    st.subheader(f"{label} : {fmt_pct(first['prevalence'])} en {y0}, {fmt_pct(last['prevalence'])} en {y1} ({rel:+.1f} %)")
else:
    st.subheader(label)

fig = go.Figure(go.Scatter(
    x=win["annee"], y=win["prevalence"], mode="lines+markers", name=SEXE_LABELS[sexe],
    line=dict(color=SEXE_COLORS[sexe], width=3), marker=dict(size=8),
    customdata=win[["effectif"]].astype("float64").to_numpy(),
    hovertemplate="%{x} : %{y:.2f} % de prévalence<br>%{customdata[0]:,.0f} patients<extra></extra>"))
if y0 <= 2020 <= y1:
    fig.add_vrect(x0=2019.5, x1=2020.5, fillcolor="#888888", opacity=0.15, line_width=0,
                  annotation_text="Covid-19", annotation_position="top left")
fig.update_layout(template="plotly_white", height=380, margin=dict(t=30, b=40),
                  xaxis=dict(title="Année", dtick=1),
                  yaxis=dict(title="Prévalence (% des bénéficiaires de la cartographie)", rangemode="tozero"))
st.plotly_chart(fig)
st.caption(f"Description du graphique : courbe de la prévalence de « {label} » ({SEXE_LABELS[sexe].lower()}), "
           f"de {fmt_pct(first['prevalence'])} en {y0} à {fmt_pct(last['prevalence'])} en {y1}.")

# --------------------------------------------------------------------------- #
# Profil par âge
# --------------------------------------------------------------------------- #
prof = profile[(profile["top"] == top) & (profile["annee"] == y1)]
total = prof[prof["sexe"] == "T"].dropna(subset=["prevalence"])
if len(total):
    peak = total.loc[total["prevalence"].idxmax()]
    st.subheader(f"Profil par âge en {y1} : pic de prévalence à {peak['age_label']} ({fmt_pct(peak['prevalence'], 1)})")
else:
    st.subheader(f"Profil par âge en {y1}")

sexes_prof = [s for s in ("H", "F") if s in set(prof["sexe"])] or ["T"]
order = prof.drop_duplicates("age_label").sort_values("age_min")["age_label"].tolist()
fig2 = go.Figure()
for s in sexes_prof:
    p = prof[prof["sexe"] == s].sort_values("age_min")
    fig2.add_trace(go.Scatter(
        x=p["age_label"], y=p["prevalence"], mode="lines+markers", name=SEXE_LABELS[s],
        line=dict(color=SEXE_COLORS[s], width=3), marker=dict(size=7),
        customdata=p[["effectif"]].astype("float64").to_numpy(),
        hovertemplate="%{x} : %{y:.2f} %<br>%{customdata[0]:,.0f} patients<extra>" + SEXE_LABELS[s] + "</extra>"))
fig2.update_layout(template="plotly_white", height=380, margin=dict(t=30, b=40),
                   xaxis=dict(title="Classe d'âge", categoryorder="array", categoryarray=order),
                   yaxis=dict(title="Prévalence (%)", rangemode="tozero"),
                   legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig2)
st.caption("Les classes d'âge où moins de 11 patients sont concernés sont masquées (secret statistique) : "
           "la courbe peut être interrompue chez les plus jeunes.")

with st.expander("Comment lire ces chiffres"):
    st.markdown(
        "- **Prévalence** : part des bénéficiaires de la cartographie pris en charge pour la pathologie. "
        "Elle est repérée à partir des soins remboursés (algorithmes de l'Assurance Maladie), ce n'est pas un diagnostic clinique.\n"
        "- **Effectifs** arrondis à la dizaine ; les effectifs inférieurs à 11 sont masqués.\n"
        "- **Non standardisée sur l'âge** : une hausse peut refléter le vieillissement de la population.\n"
        "- **2020** : un moindre recours aux soins pendant la crise sanitaire peut avoir réduit les cas repérés.")
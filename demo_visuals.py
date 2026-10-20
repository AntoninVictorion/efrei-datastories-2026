"""Page de démonstration des 4 visuels du récit (hook, contexte, insight, implication).

Lancer depuis la racine du projet : streamlit run demo_visuals.py
Les figures sont dans utils/charts.py ; ce fichier ne fait que charger les tables et brancher les filtres.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from utils import charts as ch

ROOT = Path(__file__).resolve().parent
PROC = ROOT / "data" / "processed"
TOPS = {"CAN_CAT_CAT": "Cancers", "NEU_DEM_CAT": "Démences (dont Alzheimer)", "NEU_CAT_CAT": "Maladies neurologiques"}
OUTREMER = {"971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte"}

st.set_page_config(page_title="Cancers et démences : visuels", page_icon="📈", layout="wide")


@st.cache_data(show_spinner=False)
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(PROC / f"{name}.parquet")


@st.cache_data(show_spinner=False)
def dept_names() -> dict[str, str]:
    gj = json.loads(ch.GEOJSON_PATH.read_text(encoding="utf-8"))
    return {**{f["properties"]["code"]: f["properties"]["nom"] for f in gj["features"]}, **OUTREMER}


trend_nat, trend_reg = load("trend_national"), load("trend_region")
profile, index = load("profile_age_sex"), load("index_territoire")
names = dept_names()

with st.sidebar:
    st.header("Filtres")
    top = st.selectbox("Pathologie", list(TOPS), format_func=TOPS.get)
    sexe = st.radio("Sexe", list(ch.SEXE), format_func=ch.SEXE.get)
    annee = st.slider("Année (carte et régions)", 2015, 2024, 2024)
    dept = st.selectbox("Département", sorted(names, key=lambda c: names[c]), index=sorted(names, key=lambda c: names[c]).index("59"),
                        format_func=lambda c: f"{names[c]} ({c})")
label = TOPS[top]

st.title("Cancers et démences en France : quatre visuels")

# V1 : hook
st.subheader("1. Est-ce que ça bouge ?")
terr = ch.territory_series(index, trend_reg, top, sexe, "dept", dept)
st.plotly_chart(ch.fig_trend_base100(trend_nat, terr, top, sexe, label, names[dept]))
st.caption("Base 100 en 2015 : compare des trajectoires, pas des niveaux. La courbe du département utilise la prévalence "
           "brute (effectif arrondi / population), celle de la France la prévalence publiée par la CNAM.")

# V2 : contexte
st.subheader("2. Pourquoi neutraliser l'âge ?")
st.plotly_chart(ch.fig_age_context(profile, TOPS, annee))
st.caption("Axes verticaux indépendants : les niveaux ne se comparent pas d'une facette à l'autre. "
           "Les classes d'âge à moins de 11 patients sont masquées.")

# V3 : insight
st.subheader("3. Où la charge dépasse-t-elle ce que l'âge explique ?")
st.plotly_chart(ch.fig_map_index(index, top, sexe, annee, label, selected=dept))
st.plotly_chart(ch.fig_overseas(index, top, sexe, annee))
st.caption("Indice comparatif = cas observés / cas attendus d'après l'âge. 1,2 signifie 20 % de cas de plus que ce que "
           "l'âge laisse prévoir. Zone grise : écart inférieur à ±10 %. Écart statistique, pas lecture causale.")

# V4 : implication
st.subheader("4. Quelles régions regarder en priorité ?")
st.plotly_chart(ch.fig_region_dots(index, top, sexe, annee, label))
st.caption("Traits gris : intervalle de confiance à 95 %. Un écart de plus de 10 % hors de la zone grise mérite l'attention ; "
           "il ne dit pas pourquoi.")

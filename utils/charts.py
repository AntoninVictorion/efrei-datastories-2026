"""Les 4 visuels du récit (hook, contexte, insight, implication) : figures Plotly pures.

Chaque fonction reçoit des DataFrames déjà chargés (pas d'accès disque) et renvoie une
`plotly.graph_objects.Figure`. Aucune dépendance à Streamlit : testable seule.

    V1 fig_trend_base100  Est-ce que ça bouge ?                  (hook)
    V2 fig_age_context    Pourquoi neutraliser l'âge ?            (contexte)
    V3 fig_map_index      Où la charge dépasse-t-elle l'âge ?     (insight)
       fig_overseas       Outre-mer, hors carte                    (insight)
    V4 fig_region_dots    Quelles régions regarder ?              (implication)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
from plotly.subplots import make_subplots

# --------------------------------------------------------------------------- #
# Constantes de design
# --------------------------------------------------------------------------- #
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
C_TERR = "#2a78d6"        # territoire sélectionné (bleu, slot 1)
C_FRANCE = "#52514e"      # référence France (gris foncé : neutre, jamais en concurrence)
C_HIGH, C_LOW = "#eb6834", "#2a78d6"   # pôles de l'échelle divergente
C_NEUTRAL = "#dcdbd5"     # zone ±10 % (« rien à signaler »)
SEXE = {"T": "Tous sexes", "H": "Hommes", "F": "Femmes"}
SEXE_COLOR = {"H": "#2a78d6", "F": "#eb6834", "T": "#52514e"}
SEXE_DASH = {"H": "solid", "F": "dash", "T": "solid"}   # doublon d'encodage : pas la couleur seule

IDX_MIN, IDX_MAX = 0.7, 1.3     # bornes de l'échelle (au-delà : plafonné)
BAND = 0.10                     # seuil d'écart retenu : ±10 %
OVERSEAS_DEPT = ["971", "972", "973", "974", "976"]
OVERSEAS_REGION = ["01", "02", "03", "04", "06"]
DEMENCE = "NEU_DEM_CAT"

GEOJSON_PATH = Path(__file__).resolve().parents[1] / "data" / "geo" / "departements.geojson"

_FONT = dict(family="Inter, Segoe UI, Arial, sans-serif", size=13, color=INK)


def _base_layout(fig: go.Figure, height: int, **kw) -> go.Figure:
    kw.setdefault("margin", dict(t=40, r=20, b=50, l=60))
    fig.update_layout(template="plotly_white", height=height, font=_FONT, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", hoverlabel=dict(font_size=13), **kw)
    return fig


def _fr(x: float, d: int = 2) -> str:
    """Nombre au format français (virgule décimale)."""
    return f"{x:.{d}f}".replace(".", ",")


# --------------------------------------------------------------------------- #
# V1 : tendance base 100
# --------------------------------------------------------------------------- #
def territory_series(index: pd.DataFrame, trend_region: pd.DataFrame, top: str, sexe: str,
                     level: str, code: str) -> pd.DataFrame:
    """Série annuelle (annee, prevalence, effectif) du territoire.

    Région : prévalence publiée CNAM (trend_region). Département : prévalence brute
    effectif/population de `index_territoire` (seule table départementale annuelle).
    """
    if level == "region":
        s = trend_region[(trend_region["top"] == top) & (trend_region["sexe"] == sexe)
                         & (trend_region["region"] == code)]
        return s[["annee", "prevalence", "effectif"]].sort_values("annee")
    s = index[(index["geo_level"] == "dept") & (index["top"] == top) & (index["sexe"] == sexe)
              & (index["dept"] == code)]
    return (s.rename(columns={"prevalence_brute": "prevalence", "effectif_observe": "effectif"})
             [["annee", "prevalence", "effectif"]].sort_values("annee"))


def fig_trend_base100(trend_national: pd.DataFrame, terr: pd.DataFrame, top: str, sexe: str,
                      label: str, terr_name: str, y0: int = 2015, y1: int = 2024) -> go.Figure:
    """V1. Prévalence en base 100 à l'année y0 : territoire vs France.

    La base 100 rend comparables des pathologies dont la prévalence diffère d'un facteur 5.
    Pour les démences, 2018 est annoté (déremboursement des anti-Alzheimer : rupture possible).
    """
    fr = (trend_national[(trend_national["top"] == top) & (trend_national["sexe"] == sexe)]
          [["annee", "prevalence", "effectif"]].sort_values("annee"))
    fig = go.Figure()
    series = [("France", fr, C_FRANCE, "solid")]
    if terr is not None and len(terr):
        series.append((terr_name, terr, C_TERR, "solid"))
    ends = {}
    for name, s, color, dash in series:
        s = s[(s["annee"] >= y0) & (s["annee"] <= y1)].dropna(subset=["prevalence"])
        if s.empty or s.iloc[0]["prevalence"] in (0, np.nan):
            continue
        base = s.iloc[0]["prevalence"]
        s = s.assign(b100=s["prevalence"] / base * 100)
        ends[name] = float(s.iloc[-1]["b100"])
        fig.add_trace(go.Scatter(
            x=s["annee"], y=s["b100"], mode="lines+markers", name=name,
            line=dict(color=color, width=3, dash=dash), marker=dict(size=8, line=dict(width=2, color="white")),
            customdata=np.c_[s["prevalence"], s["effectif"].astype("float64")],
            hovertemplate=("<b>" + name + "</b> · %{x}<br>Base 100 : %{y:.1f}<br>"
                           "Prévalence : %{customdata[0]:.2f} %<br>"
                           "Patients : %{customdata[1]:,.0f}<extra></extra>")))
    fig.add_hline(y=100, line=dict(color=GRID, width=1.5))
    if top == DEMENCE and y0 <= 2018 <= y1:
        fig.add_vline(x=2018, line=dict(color=INK_2, width=1.2, dash="dot"))
        fig.add_annotation(x=2018, y=1, yref="paper", yanchor="bottom", showarrow=False, xanchor="left",
                           text="Août 2018 : déremboursement des anti-Alzheimer<br>"
                                "<i>rupture possible du repérage, non vérifiée</i>",
                           font=dict(size=11, color=INK_2), align="left")
    if y0 <= 2020 <= y1:
        fig.add_vrect(x0=2019.5, x1=2020.5, fillcolor="#888888", opacity=0.12, line_width=0)
        fig.add_annotation(x=2020, y=0, yref="paper", yanchor="bottom", showarrow=False, text="Covid-19",
                           font=dict(size=11, color=INK_2))
    # étiquettes directes en bout de courbe (≤ 4 séries)
    for name, color in (("France", C_FRANCE), (terr_name, C_TERR)):
        if name in ends:
            fig.add_annotation(x=y1, y=ends[name], xanchor="left", xshift=10, showarrow=False,
                               text=f"<b>{_fr(ends[name], 1)}</b>", font=dict(color=INK, size=12))
    _base_layout(fig, 400, title=dict(text=f"{label} · évolution depuis {y0} (base 100)", x=0, font_size=15),
                 xaxis=dict(title="Année", dtick=1, range=[y0 - .3, y1 + .8], gridcolor=GRID),
                 yaxis=dict(title=f"Prévalence, base 100 en {y0}", gridcolor=GRID),
                 legend=dict(orientation="h", y=-0.22, x=0), margin=dict(t=60, r=50, b=80, l=60))
    return fig


# --------------------------------------------------------------------------- #
# V2 : small multiples par classe d'âge
# --------------------------------------------------------------------------- #
def fig_age_context(profile: pd.DataFrame, tops: dict[str, str], annee: int) -> go.Figure:
    """V2. Prévalence par classe d'âge, une facette par pathologie, courbes Hommes/Femmes.

    Axes y libres par facette : les échelles diffèrent d'un ordre de grandeur. Le message est la
    forme (la prévalence explose avec l'âge), pas la comparaison des niveaux entre facettes.
    `tops` : {code top: libellé}.
    """
    fig = make_subplots(rows=1, cols=len(tops), subplot_titles=list(tops.values()),
                        horizontal_spacing=0.07)
    for j, top in enumerate(tops, start=1):
        sub = profile[(profile["top"] == top) & (profile["annee"] == annee)]
        sexes = [s for s in ("H", "F") if s in set(sub["sexe"])] or ["T"]
        for s in sexes:
            p = sub[sub["sexe"] == s].sort_values("age_min").dropna(subset=["prevalence"])
            fig.add_trace(go.Scatter(
                x=p["age_mid"], y=p["prevalence"], mode="lines+markers", name=SEXE[s],
                legendgroup=s, showlegend=(j == 1),
                line=dict(color=SEXE_COLOR[s], width=2.5, dash=SEXE_DASH[s]), marker=dict(size=6),
                customdata=np.c_[p["age_label"], p["effectif"].astype("float64")],
                hovertemplate="<b>%{customdata[0]}</b> · " + SEXE[s] +
                              "<br>Prévalence : %{y:.2f} %<br>Patients : %{customdata[1]:,.0f}<extra></extra>"),
                row=1, col=j)
        fig.update_yaxes(title_text="Prévalence (%)" if j == 1 else None, rangemode="tozero",
                         gridcolor=GRID, row=1, col=j)
        fig.update_xaxes(title_text="Âge (milieu de classe, ans)", gridcolor=GRID, range=[0, 100], dtick=20,
                         row=1, col=j)
    for a in fig.layout.annotations:
        a.update(font=dict(size=13, color=INK), xanchor="left", x=a.x - 0.13 / len(tops))
    _base_layout(fig, 360, legend=dict(orientation="h", y=-0.3, x=0), margin=dict(t=50, r=20, b=90, l=60))
    return fig


# --------------------------------------------------------------------------- #
# V3 : carte de l'indice comparatif
# --------------------------------------------------------------------------- #
def _geojson() -> dict:
    return json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))


def diverging_scale() -> list[list]:
    """Échelle divergente plafonnée IDX_MIN-IDX_MAX, zone neutre grise entre 1-BAND et 1+BAND."""
    span = IDX_MAX - IDX_MIN
    lo, hi = (1 - BAND - IDX_MIN) / span, (1 + BAND - IDX_MIN) / span
    return [[0, "#1c4f94"], [lo, "#a9c7ee"], [lo + 1e-4, C_NEUTRAL], [hi - 1e-4, C_NEUTRAL],
            [hi, "#f6b497"], [1, "#b8431a"]]


def index_slice(index: pd.DataFrame, top: str, sexe: str, annee: int, level: str = "dept") -> pd.DataFrame:
    s = index[(index["geo_level"] == level) & (index["top"] == top) & (index["sexe"] == sexe)
              & (index["annee"] == annee)].copy()
    s["ecart_pct"] = (s["indice"] - 1) * 100
    s["rang"] = s["indice"].rank(ascending=False, method="min")
    s["n"] = s["indice"].notna().sum()
    return s


def _rings(geometry: dict):
    """Anneaux extérieurs d'un Polygon / MultiPolygon GeoJSON."""
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return [poly[0] for poly in polys]


def fig_map_index(index: pd.DataFrame, top: str, sexe: str, annee: int, label: str,
                  selected: str | None = None) -> go.Figure:
    """V3. Carte choroplèthe des départements métropolitains (outre-mer : voir fig_overseas).

    Échelle divergente centrée sur 1, plafonnée à 0,7-1,3, zone grise ±10 % (seuil retenu).
    Dessinée en polygones SVG (go.Scatter + fill) plutôt qu'avec go.Choropleth : aucune dépendance
    à un CDN de fonds de carte ni à WebGL, donc robuste au déploiement et hors ligne.
    """
    gj = _geojson()
    scale = diverging_scale()
    s = index_slice(index, top, sexe, annee).set_index("dept")
    k = np.cos(np.radians(46.5))        # correction de longitude : cartes non déformées à la latitude de la France
    fig = go.Figure()
    for f in gj["features"]:
        code, nom = f["properties"]["code"], f["properties"]["nom"]
        if code in OVERSEAS_DEPT:
            continue
        xs, ys = [], []
        for ring in _rings(f["geometry"]):
            xs += [pt[0] * k for pt in ring] + [None]
            ys += [pt[1] for pt in ring] + [None]
        r = s.loc[code] if code in s.index else None
        if r is None or pd.isna(r["indice"]):
            color, hover = "#f3f2ef", f"<b>{nom}</b> ({code})<br>Indice non disponible"
        else:
            t = (min(max(r["indice"], IDX_MIN), IDX_MAX) - IDX_MIN) / (IDX_MAX - IDX_MIN)
            color = sample_colorscale(scale, [t])[0]
            hover = (f"<b>{nom}</b> ({code})<br>Indice : <b>{_fr(r['indice'])}</b> "
                     f"[IC 95 % : {_fr(r['ic_bas'])} à {_fr(r['ic_haut'])}]<br>"
                     f"Écart à l'attendu : {r['ecart_pct']:+.0f} %<br>"
                     f"Rang : {r['rang']:.0f} / {r['n']:.0f}<br>"
                     f"Prévalence brute : {_fr(r['prevalence_brute'])} %")
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=color, hoveron="fills",
                                 line=dict(color="white", width=0.7), text=hover, hoverinfo="text",
                                 showlegend=False, name=""))
        if code == selected:      # contour renforcé du département choisi dans la sidebar
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=INK, width=2.6),
                                     hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(   # trace vide : sert uniquement à afficher la barre de couleur
        x=[None], y=[None], mode="markers", hoverinfo="skip", showlegend=False,
        marker=dict(colorscale=scale, cmin=IDX_MIN, cmax=IDX_MAX, color=[1], showscale=True, size=0,
                    colorbar=dict(title=dict(text="Indice comparatif<br>(1 = France)", side="top"),
                                  thickness=14, len=0.7, outlinewidth=0,
                                  tickvals=[0.7, 0.9, 1.0, 1.1, 1.3],
                                  ticktext=["≤ 0,7", "0,9", "1,0", "1,1", "≥ 1,3"]))))
    _base_layout(fig, 560, title=dict(text=f"{label} · {SEXE[sexe].lower()}, {annee}", x=0, font_size=15),
                 xaxis=dict(visible=False, fixedrange=True),
                 yaxis=dict(visible=False, scaleanchor="x", scaleratio=1, fixedrange=True),
                 margin=dict(t=50, r=10, b=10, l=10))
    return fig


def fig_overseas(index: pd.DataFrame, top: str, sexe: str, annee: int) -> go.Figure:
    """Encart outre-mer : indice des 5 DROM sur la même échelle de couleur (Mayotte hors échelle)."""
    s = index_slice(index, top, sexe, annee)
    s = s[s["dept"].isin(OVERSEAS_DEPT)].set_index("dept").reindex(OVERSEAS_DEPT).reset_index()
    nom = {"971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte"}
    s["nom"] = s["dept"].map(nom)
    fig = go.Figure(go.Scatter(
        x=s["nom"], y=[0] * len(s), mode="markers+text", text=[_fr(v) if pd.notna(v) else "n.d." for v in s["indice"]],
        textposition="bottom center", textfont=dict(size=13, color=INK),
        marker=dict(size=44, symbol="square", color=s["indice"], cmin=IDX_MIN, cmax=IDX_MAX,
                    colorscale=diverging_scale(), line=dict(color="white", width=2)),
        customdata=np.c_[s["ic_bas"], s["ic_haut"], s["ecart_pct"]],
        hovertemplate=("<b>%{x}</b><br>Indice : %{text} [IC 95 % : %{customdata[0]:.2f} à %{customdata[1]:.2f}]<br>"
                       "Écart à l'attendu : %{customdata[2]:+.0f} %<extra></extra>")))
    _base_layout(fig, 150, margin=dict(t=10, r=10, b=10, l=10),
                 xaxis=dict(showgrid=False, side="top", fixedrange=True, title=dict(text="Mayotte (0,17) est hors échelle : couleur plafonnée", font_size=11), ),
                 yaxis=dict(visible=False, range=[-1, 0.6]))
    return fig


# --------------------------------------------------------------------------- #
# V4 : dot plot des régions
# --------------------------------------------------------------------------- #
def fig_region_dots(index: pd.DataFrame, top: str, sexe: str, annee: int, label: str) -> go.Figure:
    """V4. Indice comparatif des 18 régions triées, avec IC 95 %, référence à 1 et bande ±10 %."""
    s = index_slice(index, top, sexe, annee, level="region").dropna(subset=["indice"])
    s = s.sort_values("indice")
    color = np.where(s["indice"] >= 1 + BAND, C_HIGH, np.where(s["indice"] <= 1 - BAND, C_LOW, "#8a8983"))
    sense = np.where(s["indice"] >= 1 + BAND, "au-dessus de l'attendu",
                     np.where(s["indice"] <= 1 - BAND, "en dessous de l'attendu", "proche de l'attendu"))
    xmin, xmax = 0.6, 1.5
    fig = go.Figure()
    fig.add_vrect(x0=1 - BAND, x1=1 + BAND, fillcolor=C_NEUTRAL, opacity=0.45, line_width=0, layer="below")
    fig.add_vline(x=1, line=dict(color=INK_2, width=1.2))
    fig.add_trace(go.Scatter(
        x=s["indice"], y=s["region_nom"], mode="markers",
        marker=dict(size=13, color=color, line=dict(width=2, color="white")),
        error_x=dict(type="data", symmetric=False, array=(s["ic_haut"] - s["indice"]).clip(lower=0),
                     arrayminus=(s["indice"] - s["ic_bas"]).clip(lower=0), color="#8a8983", thickness=1.6, width=0),
        customdata=np.c_[s["ic_bas"], s["ic_haut"], s["ecart_pct"], s["rang"], s["n"], sense],
        hovertemplate=("<b>%{y}</b><br>Indice : <b>%{x:.2f}</b> [IC 95 % : %{customdata[0]:.2f} à %{customdata[1]:.2f}]<br>"
                       "Écart : %{customdata[2]:+.0f} % (%{customdata[5]})<br>"
                       "Rang : %{customdata[3]:.0f} / %{customdata[4]:.0f}<extra></extra>"),
        showlegend=False))
    for r in s[s["indice"] < xmin].itertuples():     # ex. Mayotte pour les démences : hors cadre
        fig.add_annotation(x=xmin, y=r.region_nom, text=f"◄ {_fr(r.indice)}", showarrow=False, xanchor="left",
                           font=dict(size=11, color=INK_2))
    fig.add_annotation(x=1 + BAND, y=1.0, yref="paper", yanchor="bottom", text="zone ±10 %", showarrow=False,
                       font=dict(size=11, color=INK_2))
    _base_layout(fig, 560, title=dict(text=f"{label} · indice par région, {annee}", x=0, font_size=15),
                 xaxis=dict(title="Indice comparatif (1 = France, âge neutralisé)", range=[xmin, xmax],
                            gridcolor=GRID, dtick=0.1),
                 yaxis=dict(title=None, categoryorder="array", categoryarray=list(s["region_nom"]), gridcolor=GRID),
                 margin=dict(t=60, r=20, b=60, l=190))
    return fig

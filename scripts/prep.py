"""Construit les tables prêtes à afficher pour l'application Streamlit.

Entrées : data/processed/facts.parquet et dim_pathologie.parquet (voir build_facts.py)
Sorties : data/processed/
    trend_national.parquet    France, tous âges : effectif, population, prévalence par pathologie/sexe/année
    trend_region.parquet      Idem par région
    profile_age_sex.parquet   France, par classe d'âge : profil de prévalence
    index_territoire.parquet  Indice comparatif (observé / attendu) par département et par région
    prep_report.json          Contrôles de calibration, volumétrie, aperçu des résultats

Règles de calcul (issues des diagnostics sur les données) :
  R1. Prévalence affichée = prév. publiée par la CNAM (calculée sur les effectifs exacts).
      Repli sur ntop / npop si elle est absente. Les effectifs publiés sont arrondis à 10.
  R2. Chaque niveau géographique utilise sa propre ligne publiée : on ne recalcule jamais
      un total régional ou national à partir du niveau inférieur (écarts jusqu'à ~2 %).
  R3. Dénominateur = Npop de la ligne (pour le sein et la prostate en « tous sexes »,
      il est restreint au sexe concerné : ce n'est pas une erreur).
  R4. Indice comparatif = observé / attendu (standardisation indirecte).
        observé  = effectif « tous âges » du territoire (rarement masqué)
        attendu  = somme sur les classes d'âge de  Npop(territoire, âge) x prévalence nationale(âge)
      (mêmes pathologie, sexe et année). Indice 1,2 = 20 % de cas de plus que ce que l'âge
      de la population laisserait prévoir. Robuste au masquage car Npop n'est jamais masqué.
  R5. Intervalle de confiance à 95 % de l'indice : approximation de Byar (loi de Poisson).

Usage (depuis la racine du projet) :
    python scripts/prep.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
ALL_AGES = "tsage"
Z95 = 1.959964
KEYS = ["annee", "top", "sexe"]

# Codes région INSEE (nouvelle nomenclature). Le code 99 (« France entière ») n'est pas listé.
REGION_NAMES = {
    "01": "Guadeloupe", "02": "Martinique", "03": "Guyane", "04": "La Réunion", "06": "Mayotte",
    "11": "Île-de-France", "24": "Centre-Val de Loire", "27": "Bourgogne-Franche-Comté",
    "28": "Normandie", "32": "Hauts-de-France", "44": "Grand Est", "52": "Pays de la Loire",
    "53": "Bretagne", "75": "Nouvelle-Aquitaine", "76": "Occitanie", "84": "Auvergne-Rhône-Alpes",
    "93": "Provence-Alpes-Côte d'Azur", "94": "Corse",
}


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #
def _prev(df: pd.DataFrame) -> pd.Series:
    """R1 : prévalence CNAM, repli sur la prévalence recalculée (en %)."""
    return df["prev_cnam"].astype("float64").fillna(df["prev_calc"].astype("float64"))


def _plain(df: pd.DataFrame) -> pd.DataFrame:
    """Catégories -> chaînes (plus simple et plus sûr côté application)."""
    out = df.copy()
    for col in out.columns:
        if isinstance(out[col].dtype, pd.CategoricalDtype):
            out[col] = out[col].astype(str)
    return out.reset_index(drop=True)


def _with_labels(df: pd.DataFrame, dim: pd.DataFrame) -> pd.DataFrame:
    small = dim[["top", "famille", "niveau", "label", "type_code"]]
    return df.merge(small, on="top", how="left")


def _region_name(codes: pd.Series) -> pd.Series:
    s = codes.astype(str)
    return s.map(REGION_NAMES).fillna(s)


def _age_info(code: str) -> tuple[int, float, str]:
    lo = int(code[:2])
    if code.endswith("et+"):
        return lo, lo + 2.0, f"{lo} ans et +"
    hi = int(code[3:5])
    return lo, (lo + hi) / 2, f"{lo}-{hi} ans"


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def build_trend(f: pd.DataFrame, level: str) -> pd.DataFrame:
    sub = f[(f["geo_level"] == level) & (f["age"] == ALL_AGES)]
    cols = KEYS + (["region"] if level == "region" else []) + ["ntop", "npop", "masked"]
    out = sub[cols].copy()
    out["prevalence"] = _prev(sub)
    out = out.rename(columns={"ntop": "effectif", "npop": "population", "masked": "masque"})
    if level == "region":
        out["region_nom"] = _region_name(out["region"])
    return out


def build_profile(f: pd.DataFrame) -> pd.DataFrame:
    sub = f[(f["geo_level"] == "france") & (f["age"] != ALL_AGES)]
    out = sub[KEYS + ["age", "ntop", "npop", "masked"]].copy()
    out["prevalence"] = _prev(sub)
    out = out.rename(columns={"ntop": "effectif", "npop": "population", "masked": "masque"})
    info = {c: _age_info(c) for c in out["age"].astype(str).unique()}
    codes = out["age"].astype(str)
    out["age_min"] = codes.map(lambda c: info[c][0])
    out["age_mid"] = codes.map(lambda c: info[c][1])
    out["age_label"] = codes.map(lambda c: info[c][2])
    return out


def _byar(observed: np.ndarray, expected: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """R5 : bornes de l'IC 95 % de l'indice observé/attendu (approximation de Byar)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        lo = np.where(observed > 0,
                      observed * (1 - 1 / (9 * observed) - Z95 / (3 * np.sqrt(observed))) ** 3, 0.0) / expected
        hi = (observed + 1) * (1 - 1 / (9 * (observed + 1)) + Z95 / (3 * np.sqrt(observed + 1))) ** 3 / expected
    bad = np.isnan(observed) | ~(expected > 0)
    lo[bad] = np.nan
    hi[bad] = np.nan
    return lo, hi


def build_index(f: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """R4 : indice comparatif par département et par région."""
    nat = f[(f["geo_level"] == "france") & (f["age"] != ALL_AGES)]
    nat = nat.assign(prev_nat=_prev(nat) / 100)[KEYS + ["age", "prev_nat"]]

    parts, diag = [], {}
    for level in ("dept", "region"):
        terr = ["region", "dept"] if level == "dept" else ["region"]
        det = f[(f["geo_level"] == level) & (f["age"] != ALL_AGES)][KEYS + ["age"] + terr + ["npop"]]
        m = det.merge(nat, on=KEYS + ["age"], how="left")
        diag[f"part_cellules_sans_prevalence_nationale_{level}"] = round(float(m["prev_nat"].isna().mean()), 5)
        m["part"] = m["npop"].astype("float64") * m["prev_nat"].fillna(0.0)
        expected = m.groupby(KEYS + terr, observed=True)["part"].sum().rename("effectif_attendu").reset_index()

        obs = f[(f["geo_level"] == level) & (f["age"] == ALL_AGES)][
            KEYS + terr + ["ntop", "npop", "prev_cnam", "prev_calc"]]
        res = obs.merge(expected, on=KEYS + terr, how="left")
        res["effectif_observe"] = res["ntop"].astype("float64")
        res["population"] = res["npop"]
        res["prevalence_brute"] = _prev(res)
        O = res["effectif_observe"].to_numpy()
        E = res["effectif_attendu"].to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            res["indice"] = np.where(E > 0, O / E, np.nan)
        lo, hi = _byar(O, E)
        res["ic_bas"], res["ic_haut"] = lo, hi
        res["significatif"] = (lo > 1) | (hi < 1)
        if level == "region":
            res["dept"] = "999"
        res["geo_level"] = level
        parts.append(res.drop(columns=["ntop", "npop", "prev_cnam", "prev_calc"]))

    out = pd.concat([_plain(p) for p in parts], ignore_index=True)
    out["region_nom"] = _region_name(out["region"])
    return out, diag


# --------------------------------------------------------------------------- #
# Contrôles et aperçu
# --------------------------------------------------------------------------- #
def calibration(f: pd.DataFrame, index: pd.DataFrame) -> dict:
    """Σ attendu des départements ≈ observé France : vérifie la cohérence de la méthode."""
    fr = f[(f["geo_level"] == "france") & (f["age"] == ALL_AGES)][KEYS + ["ntop"]].copy()
    fr = _plain(fr).rename(columns={"ntop": "obs_france"})
    d = index[index["geo_level"] == "dept"].groupby(KEYS)["effectif_attendu"].sum().reset_index()
    c = d.merge(fr, on=KEYS, how="inner")
    c["ratio"] = c["effectif_attendu"] / c["obs_france"].astype("float64")
    q = c["ratio"].quantile([0, 0.05, 0.5, 0.95, 1]).round(4)
    return {
        "attendu_departements_sur_observe_france": {
            "min": float(q.iloc[0]), "p5": float(q.iloc[1]), "mediane": float(q.iloc[2]),
            "p95": float(q.iloc[3]), "max": float(q.iloc[4]), "n_combinaisons": int(len(c))},
        "lecture": "proche de 1 = méthode cohérente ; l'écart restant vient des classes d'âge masquées "
                   "au niveau national et des patients non rattachés à un département",
    }


def highlights(trend: pd.DataFrame, index: pd.DataFrame) -> list[str]:
    L: list[str] = []
    first, last = int(trend["annee"].min()), int(trend["annee"].max())
    for top, nom in (("CAN_CAT_CAT", "Cancers (tous)"), ("NEU_CAT_CAT", "Maladies neurologiques (toutes)"),
                     ("NEU_DEM_CAT", "Démences (dont Alzheimer)")):
        sub = trend[(trend["top"] == top) & (trend["sexe"] == "T")].set_index("annee")
        if first in sub.index and last in sub.index:
            a, b = sub.loc[first, "prevalence"], sub.loc[last, "prevalence"]
            L.append(f"{nom} : prévalence nationale {a:.2f} % en {first} -> {b:.2f} % en {last}"
                     f" ({(b / a - 1) * 100:+.1f} %)")
    top, nom = "NEU_DEM_CAT", "démences"
    sub = index[(index["geo_level"] == "dept") & (index["top"] == top) & (index["sexe"] == "T")
                & (index["annee"] == last)].dropna(subset=["indice"]).sort_values("indice")
    if len(sub):
        def fmt(r):
            return (f"dép. {r['dept']} ({r['region_nom']}) indice {r['indice']:.2f} "
                    f"[{r['ic_bas']:.2f}-{r['ic_haut']:.2f}]")
        L.append(f"Indice comparatif {nom} {last}, tous sexes : {int(sub['significatif'].sum())} départements "
                 f"significativement différents de la France sur {len(sub)}")
        L.append("  plus bas : " + " ; ".join(fmt(r) for _, r in sub.head(3).iterrows()))
        L.append("  plus haut : " + " ; ".join(fmt(r) for _, r in sub.tail(3).iloc[::-1].iterrows()))
    return L


# --------------------------------------------------------------------------- #
def main() -> None:
    fpath, dpath = PROC / "facts.parquet", PROC / "dim_pathologie.parquet"
    if not (fpath.exists() and dpath.exists()):
        sys.exit("facts.parquet / dim_pathologie.parquet introuvables : lancer d'abord build_facts.py.")
    f = pd.read_parquet(fpath)
    dim = pd.read_parquet(dpath)

    trend_nat = _with_labels(_plain(build_trend(f, "france")), dim)
    trend_reg = _with_labels(_plain(build_trend(f, "region")), dim)
    profile = _with_labels(_plain(build_profile(f)), dim)
    index, diag = build_index(f)
    index = _with_labels(index, dim)

    tables = {"trend_national": trend_nat, "trend_region": trend_reg,
              "profile_age_sex": profile, "index_territoire": index}
    for name, df in tables.items():
        df.to_parquet(PROC / f"{name}.parquet", index=False)

    report = {
        "regles": ["R1 prévalence CNAM avec repli sur le recalcul", "R2 aucun total recalculé",
                   "R3 dénominateur = Npop de la ligne", "R4 indice comparatif par standardisation indirecte",
                   "R5 IC 95 % de Byar"],
        "tables": {n: {"lignes": int(len(d)), "mo": round((PROC / f"{n}.parquet").stat().st_size / 1e6, 2)}
                   for n, d in tables.items()},
        "indice": {
            **diag,
            "part_observe_masque": round(float(index["effectif_observe"].isna().mean()), 5),
            "part_significatif": round(float(index["significatif"].mean()), 4),
        },
        "calibration": calibration(f, index),
    }
    lines = highlights(trend_nat, index)
    report["apercu"] = lines
    (PROC / "prep_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Tables écrites :")
    for n, info in report["tables"].items():
        print(f"  {n:18s} {info['lignes']:>9,} lignes  {info['mo']:>6.2f} Mo")
    cal = report["calibration"]["attendu_departements_sur_observe_france"]
    print(f"Calibration (attendu des départements / observé France) : médiane {cal['mediane']}, "
          f"min {cal['min']}, max {cal['max']}")
    print("Aperçu :")
    for line in lines:
        print("  " + line)


if __name__ == "__main__":
    main()
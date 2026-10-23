"""Construit la table de faits propre (périmètre : cancers + maladies neurologiques)
et un rapport de qualité réutilisable dans l'application.

Entrée  : data/raw/effectifs.csv (voir download_data.py)
Sorties : data/processed/facts.parquet           faits typés, masquage explicite
          data/processed/dim_pathologie.parquet  dimension des pathologies
          data/processed/quality_report.json     contrôles de cohérence et de qualité

Conventions de la table de faits :
  - geo_level : 'dept' (département), 'region' (dept == 999 : total régional),
                'france' (region == 99 : HYPOTHÈSE « France entière », vérifiée dans le rapport)
  - ntop      : effectif de patients ; <NA> quand la valeur est masquée (secret statistique)
  - prev_calc : prévalence recalculée = ntop / npop * 100 (transparente, notre référence)
  - prev_cnam : prévalence publiée par la CNAM (conservée pour contrôle uniquement)
  - sexe      : H / F / T (tous sexes) ; age : classes de 5 ans ou 'tsage' (tous âges)

Usage (depuis la racine du projet) :
    python scripts/build_facts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import union_categoricals

ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = ROOT / "data" / "raw" / "effectifs.csv"
META_FILE = ROOT / "data" / "raw" / "effectifs.meta.txt"
OUT_DIR = ROOT / "data" / "processed"

SEP = ";"
CHUNK_ROWS = 500_000
SCOPE = ["Cancers", "Maladies neurologiques"]
USECOLS = ["annee", "patho_niv1", "patho_niv2", "patho_niv3", "top", "cla_age_5",
           "libelle_sexe", "region", "dept", "Ntop", "Npop", "prev"]
SEXE_MAP = {"hommes": "H", "femmes": "F", "tous sexes": "T"}
FRANCE_REGION = "99"      # hypothèse : « France entière » (contrôlée dans le rapport)
ALL_DEPT = "999"          # total régional
ALL_AGES = "tsage"
PREV_TOLERANCE = 0.05     # points de pourcentage


# --------------------------------------------------------------------------- #
# Chargement et nettoyage
# --------------------------------------------------------------------------- #
def _num(s: pd.Series, issues: dict, name: str) -> pd.Series:
    """Conversion numérique ; compte les valeurs non vides qui ne se convertissent pas."""
    s = s.str.replace(",", ".", regex=False)
    out = pd.to_numeric(s, errors="coerce")
    bad = int((out.isna() & (s != "")).sum())
    if bad:
        issues[name] = issues.get(name, 0) + bad
    return out


def _compact(sc: pd.DataFrame, issues: dict) -> pd.DataFrame:
    """Typage compact d'un morceau (catégories, entiers, flottants 32 bits)."""
    sexe = sc["libelle_sexe"].map(SEXE_MAP)
    if sexe.isna().any():
        bad = sorted(sc.loc[sexe.isna(), "libelle_sexe"].unique())
        raise ValueError(f"libellés de sexe inattendus : {bad}")
    region, dept = sc["region"], sc["dept"]
    geo = np.where(region == FRANCE_REGION, "france", np.where(dept == ALL_DEPT, "region", "dept"))
    return pd.DataFrame({
        "annee": pd.to_numeric(sc["annee"]).astype("int16"),
        "famille": sc["patho_niv1"].astype("category"),
        "top": sc["top"].astype("category"),
        "age": sc["cla_age_5"].astype("category"),
        "sexe": sexe.astype("category"),
        "geo_level": pd.Series(geo, index=sc.index).astype("category"),
        "region": region.astype("category"),
        "dept": dept.astype("category"),
        "ntop": _num(sc["Ntop"], issues, "Ntop").round().astype("Int32"),
        "npop": _num(sc["Npop"], issues, "Npop").round().astype("Int32"),
        "prev_cnam": _num(sc["prev"], issues, "prev").astype("float32"),
    }).reset_index(drop=True)


def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatène des morceaux en conservant les colonnes catégorielles."""
    data = {}
    for col in parts[0].columns:
        series = [p[col] for p in parts]
        if isinstance(series[0].dtype, pd.CategoricalDtype):
            data[col] = pd.Series(union_categoricals(series, ignore_order=True))
        else:
            data[col] = pd.concat(series, ignore_index=True)
    return pd.DataFrame(data)


def load_scope() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Lit le CSV par morceaux, ne garde que le périmètre. Retourne (faits, dim brute, anomalies)."""
    if not RAW_FILE.exists():
        sys.exit("CSV introuvable : lancer d'abord `python scripts/download_data.py download`.")
    parts, dims, issues = [], [], {}
    n_read = 0
    reader = pd.read_csv(RAW_FILE, sep=SEP, dtype=str, keep_default_na=False,
                         encoding="utf-8-sig", usecols=USECOLS, chunksize=CHUNK_ROWS)
    for chunk in reader:
        n_read += len(chunk)
        sc = chunk[chunk["patho_niv1"].isin(SCOPE)]
        if not sc.empty:
            dims.append(sc[["top", "patho_niv1", "patho_niv2", "patho_niv3"]].drop_duplicates())
            parts.append(_compact(sc, issues))
        print(f"\r  {n_read:,} lignes lues", end="", flush=True)
    print()
    if not parts:
        sys.exit("Aucune ligne dans le périmètre : vérifier les libellés de patho_niv1.")
    facts = _concat(parts)
    return facts, pd.concat(dims, ignore_index=True), issues


def build_dim(dim_raw: pd.DataFrame) -> pd.DataFrame:
    """Dimension des pathologies : niveau (categorie / type / actif / surveillance) et libellé court."""
    dim = dim_raw.drop_duplicates("top").rename(
        columns={"patho_niv1": "famille", "patho_niv2": "niv2", "patho_niv3": "niv3"}
    ).reset_index(drop=True)
    code = dim["top"]
    dim["niveau"] = np.select(
        [dim["niv2"] == "", code.str.endswith("_ACT"), code.str.endswith("_SUR")],
        ["categorie", "actif", "surveillance"], default="type")
    dim["label"] = np.where(dim["niv3"] != "", dim["niv3"],
                            np.where(dim["niv2"] != "", dim["niv2"], dim["famille"]))
    dim["type_code"] = code.str[:7]          # ex. CAN_BPU : regroupe _CAT / _ACT / _SUR
    return dim.sort_values("top").reset_index(drop=True)


def add_derived(facts: pd.DataFrame) -> pd.DataFrame:
    ntop = facts["ntop"].astype("float64")
    npop = facts["npop"].astype("float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        facts["prev_calc"] = np.where(npop > 0, ntop / npop * 100, np.nan).astype("float32")
    facts["masked"] = facts["ntop"].isna()
    return facts


# --------------------------------------------------------------------------- #
# Contrôles de qualité
# --------------------------------------------------------------------------- #
def _share(masked: int, n: int) -> float:
    return round(masked / n, 4) if n else float("nan")


def check_masking(f: pd.DataFrame) -> dict:
    out: dict = {}
    g = f.assign(tous_ages=f["age"].eq(ALL_AGES)).groupby(
        ["geo_level", "tous_ages"], observed=True)["masked"].agg(["size", "sum"])
    out["par_niveau_geo_et_tous_ages"] = {
        f"{geo}|tous_ages={ta}": {"lignes": int(r["size"]), "masquees": int(r["sum"]),
                                  "part": _share(int(r["sum"]), int(r["size"]))}
        for (geo, ta), r in g.iterrows()}
    d = f[(f["geo_level"] == "dept") & (f["age"] != ALL_AGES)]
    a = d.groupby("age", observed=True)["masked"].agg(["size", "sum"])
    out["departements_par_classe_age"] = {
        str(age): _share(int(r["sum"]), int(r["size"])) for age, r in a.iterrows()}
    fam = f[f["geo_level"] == "dept"].groupby(["famille", "annee"], observed=True)["masked"].mean()
    out["departements_part_masquee_famille_annee"] = {
        f"{fa}|{an}": round(float(v), 4) for (fa, an), v in fam.items()}
    return out


def check_prev(f: pd.DataFrame) -> dict:
    ok = f[f["ntop"].notna() & f["prev_cnam"].notna() & f["prev_calc"].notna()].copy()
    ok["gap"] = ok["prev_cnam"].astype("float64") - ok["prev_calc"].astype("float64")
    ok["abs_gap"] = ok["gap"].abs()
    ok["tous_ages"] = ok["age"].eq(ALL_AGES)
    with np.errstate(divide="ignore", invalid="ignore"):
        ok["ratio"] = np.where(ok["prev_calc"] > 0,
                               ok["prev_cnam"].astype("float64") / ok["prev_calc"].astype("float64"),
                               np.nan)
    out = {"lignes_comparees": int(len(ok)),
           "part_ecart_sup_tolerance": round(float((ok["abs_gap"] > PREV_TOLERANCE).mean()), 4),
           "ecart_abs_max": round(float(ok["abs_gap"].max()), 4) if len(ok) else None,
           "groupes": {}}
    for (ta, sx, geo), sub in ok.groupby(["tous_ages", "sexe", "geo_level"], observed=True):
        if len(sub) == 0:
            continue
        out["groupes"][f"tous_ages={ta}|sexe={sx}|{geo}"] = {
            "n": int(len(sub)),
            "part_ecart_sup_tolerance": round(float((sub["abs_gap"] > PREV_TOLERANCE).mean()), 4),
            "ecart_median": round(float(sub["gap"].median()), 4),
            "ecart_abs_p95": round(float(sub["abs_gap"].quantile(0.95)), 4),
            "ecart_abs_max": round(float(sub["abs_gap"].max()), 4),
            "ratio_prev_cnam_sur_calc_median": round(float(sub["ratio"].median()), 4),
        }
    return out


def _sums(sub: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    s = sub.assign(ntop_f=sub["ntop"].astype("float64"))
    return s.groupby(by, observed=True)["ntop_f"].agg(["sum", "count", "size"])


def check_geography(f: pd.DataFrame) -> dict:
    """Région 99 = somme des régions ? Somme des départements = total régional ?"""
    out: dict = {}
    for top in ("CAN_CAT_CAT", "NEU_CAT_CAT", "NEU_DEM_CAT"):
        sub = f[(f["top"] == top) & (f["age"] == ALL_AGES) & (f["sexe"] == "T")].copy()
        if sub.empty:
            continue
        sub["region"] = sub["region"].astype(str)
        fr = sub[sub["geo_level"] == "france"].set_index("annee")["ntop"].astype("float64")
        rg = _sums(sub[sub["geo_level"] == "region"], ["annee"])
        rg = rg[rg["count"] == rg["size"]]              # années où aucune région n'est masquée
        ratio_fr = (fr / rg["sum"]).dropna().round(4)
        dp = _sums(sub[sub["geo_level"] == "dept"], ["annee", "region"])
        dp = dp[dp["count"] == dp["size"]]              # régions dont aucun département n'est masqué
        rr = sub[sub["geo_level"] == "region"].set_index(["annee", "region"])["ntop"].astype("float64")
        ratio_dp = (rr.reindex(dp.index) / dp["sum"]).dropna()
        out[top] = {
            "france_sur_somme_des_regions_par_annee": {int(k): float(v) for k, v in ratio_fr.items()},
            "total_regional_sur_somme_departements": {
                "regions_annees_comparables": int(len(ratio_dp)),
                "mediane": round(float(ratio_dp.median()), 4) if len(ratio_dp) else None,
                "min": round(float(ratio_dp.min()), 4) if len(ratio_dp) else None,
                "max": round(float(ratio_dp.max()), 4) if len(ratio_dp) else None,
            },
        }
    return out


def check_cat_vs_act_sur(f: pd.DataFrame, dim: pd.DataFrame) -> dict:
    """(actif + sous surveillance) / catégorie, au niveau France, tous âges, tous sexes."""
    out: dict = {}
    base = f[(f["geo_level"] == "france") & (f["age"] == ALL_AGES) & (f["sexe"] == "T")]
    for tc, grp in dim[dim["famille"] == "Cancers"].groupby("type_code"):
        codes = dict(zip(grp["niveau"], grp["top"]))
        if not {"type", "actif", "surveillance"} <= set(codes):
            continue
        piv = base[base["top"].isin(list(codes.values()))].assign(
            ntop_f=lambda d: d["ntop"].astype("float64")).pivot_table(
            index="annee", columns="top", values="ntop_f", aggfunc="sum", observed=True)
        try:
            ratio = (piv[codes["actif"]] + piv[codes["surveillance"]]) / piv[codes["type"]]
        except KeyError:
            continue
        out[tc] = {int(k): round(float(v), 4) for k, v in ratio.dropna().items()}
    return out


def check_npop(f: pd.DataFrame) -> dict:
    out: dict = {}
    keys = ["annee", "age", "sexe", "region", "dept"]
    nun = f.groupby(keys, observed=True)["npop"].nunique()
    out["part_cellules_npop_differant_selon_pathologie"] = round(float((nun > 1).mean()), 4)
    sub = f[(f["top"] == "CAN_CAT_CAT") & (f["geo_level"] == "france")].copy()
    if not sub.empty:
        sub["npop_f"] = sub["npop"].astype("float64")
        tot = sub[(sub["age"] == ALL_AGES) & (sub["sexe"] == "T")].set_index("annee")["npop_f"]
        det = sub[(sub["age"] != ALL_AGES) & (sub["sexe"] == "T")].groupby("annee", observed=True)["npop_f"].sum()
        out["france_npop_tous_ages_sur_somme_classes"] = {
            int(k): round(float(v), 4) for k, v in (tot / det).dropna().items()}
        h = sub[(sub["age"] == ALL_AGES) & (sub["sexe"] == "H")].set_index("annee")["npop_f"]
        fe = sub[(sub["age"] == ALL_AGES) & (sub["sexe"] == "F")].set_index("annee")["npop_f"]
        out["france_npop_tous_sexes_sur_h_plus_f"] = {
            int(k): round(float(v), 4) for k, v in (tot / (h + fe)).dropna().items()}
    return out

def check_duplicates(f: pd.DataFrame) -> dict:
    key = ["annee", "top", "sexe", "age", "geo_level", "region", "dept"]
    return {"cle": key,
            "lignes_dupliquees": int(f.duplicated(key).sum()),
            "valeurs_manquantes": {c: int(f[c].isna().sum()) for c in ("ntop", "npop")}}


# --------------------------------------------------------------------------- #
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    facts, dim_raw, issues = load_scope()
    dim = build_dim(dim_raw)
    facts = add_derived(facts)

    facts.to_parquet(OUT_DIR / "facts.parquet", compression="zstd", index=False)
    dim.to_parquet(OUT_DIR / "dim_pathologie.parquet", index=False)

    print("Contrôles de qualité…")
    meta = {}
    if META_FILE.exists():
        meta = dict(line.split(": ", 1) for line in META_FILE.read_text(encoding="utf-8").splitlines()
                    if ": " in line)
    report = {
        "source": meta,
        "resume": {
            "lignes_perimetre": int(len(facts)),
            "annees": [int(facts["annee"].min()), int(facts["annee"].max())],
            "pathologies_top": int(facts["top"].nunique()),
            "lignes_par_niveau_geo": {str(k): int(v) for k, v in facts["geo_level"].value_counts().items()},
            "valeurs_non_numeriques_ignorees": issues,
        },
        "masquage": check_masking(facts),
        "prevalence_cnam_vs_recalculee": check_prev(facts),
        "geographie": check_geography(facts),
        "categorie_vs_actif_plus_surveillance": check_cat_vs_act_sur(facts, dim),
        "population_npop": check_npop(facts),
        "doublons_et_manquants": check_duplicates(facts),
    }
    (OUT_DIR / "quality_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for name in ("facts.parquet", "dim_pathologie.parquet", "quality_report.json"):
        print(f"  {name} : {(OUT_DIR / name).stat().st_size / 1e6:.1f} Mo")
    print(f"Lignes du périmètre : {len(facts):,}")


if __name__ == "__main__":
    main()
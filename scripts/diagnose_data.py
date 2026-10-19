"""Diagnostics ciblés sur data/processed/facts.parquet.

Deux questions ouvertes après build_facts.py :
  A. Npop (population de référence) varie-t-il selon la pathologie pour une même cellule
     (annee, age, sexe, region, dept) ? Si oui, pour quelles pathologies, quels sexes, quels niveaux ?
  B. D'où vient l'écart entre la prévalence publiée (prev_cnam) et celle recalculée
     (ntop / npop * 100) sur les lignes détaillées (hors « tous âges ») ?
     Hypothèses testées : petites populations, arrondi des effectifs, dénominateur différent.

Usage (depuis la racine du projet) :
    python scripts/diagnose_data.py
Sortie : data/processed/diagnostic.txt (et affichage à l'écran)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "processed" / "facts.parquet"
OUT = ROOT / "data" / "processed" / "diagnostic.txt"

REF_TOP = "CAN_CAT_CAT"                       # pathologie de référence pour comparer Npop
KEYS = ["annee", "age", "sexe", "region", "dept"]
ALL_AGES = "tsage"
TOL = 0.05                                    # points de pourcentage


def pct(x: float) -> str:
    return f"{100 * x:6.2f} %"


def main() -> None:
    if not FACTS.exists():
        sys.exit("facts.parquet introuvable : lancer d'abord `python scripts/build_facts.py`.")
    f = pd.read_parquet(FACTS)
    n0 = len(f)

    ref = f.loc[f["top"] == REF_TOP, KEYS + ["npop"]].rename(columns={"npop": "npop_ref"})
    if ref.empty:
        sys.exit(f"Pathologie de référence {REF_TOP} absente.")
    f = f.merge(ref, on=KEYS, how="left")
    assert len(f) == n0, "la fusion a modifié le nombre de lignes (clé de référence non unique ?)"

    f["npop_f"] = f["npop"].astype("float64")
    f["ref_f"] = f["npop_ref"].astype("float64")
    f["differs"] = f["ref_f"].notna() & (f["npop_f"] != f["ref_f"])
    with np.errstate(divide="ignore", invalid="ignore"):
        f["rel"] = (f["npop_f"] - f["ref_f"]).abs() / f["ref_f"]

    L: list[str] = ["DIAGNOSTIC - facts.parquet", f"Lignes : {n0:,} | référence Npop : {REF_TOP}", ""]

    # ---------------- A. Npop selon la pathologie ----------------
    L.append("== A. Npop différent de celui de la pathologie de référence")
    L.append(f"  Part des lignes concernées : {pct(f['differs'].mean())}")
    by_top = f.groupby("top", observed=True)["differs"].mean()
    diff_tops = by_top[by_top > 0].sort_values(ascending=False)
    L.append(f"  Pathologies concernées : {len(diff_tops)} sur {by_top.shape[0]}")
    for top, share in diff_tops.items():
        sub = f[(f["top"] == top) & f["differs"]]
        L.append(f"    {top} : {pct(share)} des lignes | écart relatif médian {sub['rel'].median():.4f}"
                 f" | max {sub['rel'].max():.4f}")
    L.append("  Par sexe : " + " | ".join(
        f"{k}={pct(v).strip()}" for k, v in f.groupby("sexe", observed=True)["differs"].mean().items()))
    L.append("  Par niveau géographique : " + " | ".join(
        f"{k}={pct(v).strip()}" for k, v in f.groupby("geo_level", observed=True)["differs"].mean().items()))
    L.append("  Tous âges / classes détaillées : " + " | ".join(
        f"{'tous âges' if k else 'détaillé'}={pct(v).strip()}"
        for k, v in f.groupby(f["age"].eq(ALL_AGES), observed=True)["differs"].mean().items()))
    L.append("  Lignes masquées / non masquées : " + " | ".join(
        f"{'masquée' if k else 'non masquée'}={pct(v).strip()}"
        for k, v in f.groupby("masked", observed=True)["differs"].mean().items()))
    L.append("")

    # ---------------- B. Écart prev publiée vs recalculée ----------------
    d = f[f["ntop"].notna() & f["prev_cnam"].notna() & f["prev_calc"].notna()
          & (f["age"] != ALL_AGES) & f["geo_level"].isin(["dept", "region"])].copy()
    d["gap"] = d["prev_cnam"].astype("float64") - d["prev_calc"].astype("float64")
    d["big"] = d["gap"].abs() > TOL
    d["ntop_i"] = d["ntop"].astype("int64")
    L.append("== B. Écart prev_cnam vs ntop/npop*100 (lignes détaillées, départements et régions)")
    L.append(f"  Lignes comparées : {len(d):,} | écart > {TOL} point : {pct(d['big'].mean())}")

    L.append("  B1. Selon la taille de la population (déciles de npop) :")
    d["npop_bin"] = pd.qcut(d["npop_f"], 10, duplicates="drop")
    for b, sub in d.groupby("npop_bin", observed=True):
        L.append(f"    {str(b):>22} : écart>tol {pct(sub['big'].mean())} | |écart| médian {sub['gap'].abs().median():.4f}")

    L.append("  B2. Selon l'effectif de patients :")
    d["ntop_bin"] = pd.cut(d["ntop_i"], [10, 19, 49, 99, 499, np.inf],
                           labels=["11-19", "20-49", "50-99", "100-499", "500+"])
    for b, sub in d.groupby("ntop_bin", observed=True):
        L.append(f"    {str(b):>8} : écart>tol {pct(sub['big'].mean())} (n={len(sub):,})")

    L.append("  B3. Effectifs arrondis ? (part de ntop multiple de 5 / de 10)")
    for label, sub in (("écart > tol", d[d["big"]]), ("écart <= tol", d[~d["big"]])):
        if len(sub):
            L.append(f"    {label:>12} : multiple de 5 = {pct((sub['ntop_i'] % 5 == 0).mean()).strip()}"
                     f" | multiple de 10 = {pct((sub['ntop_i'] % 10 == 0).mean()).strip()}")

    L.append("  B4. Effectif implicite (prev_cnam * npop / 100) moins ntop, sur les lignes à écart > tol :")
    big = d[d["big"]]
    if len(big):
        implied = big["prev_cnam"].astype("float64") / 100 * big["npop_f"]
        diff = implied - big["ntop_i"]
        q = diff.quantile([0.05, 0.25, 0.5, 0.75, 0.95]).round(1).to_dict()
        L.append(f"    quantiles 5/25/50/75/95 % : {list(q.values())}")
        L.append(f"    part où |écart| <= 0,5 patient : {pct((diff.abs() <= 0.5).mean()).strip()}"
                 f" | <= 5 patients : {pct((diff.abs() <= 5).mean()).strip()}")

        L.append("  B5. Dénominateur de référence ?")
        with np.errstate(divide="ignore", invalid="ignore"):
            prev_ref = big["ntop_i"] / big["ref_f"] * 100
        ok_ref = (big["prev_cnam"].astype("float64") - prev_ref).abs() <= TOL
        L.append(f"    part des écarts qui disparaissent avec le Npop de {REF_TOP} : {pct(ok_ref.mean()).strip()}")
        L.append(f"    part des écarts où le Npop diffère de la référence : {pct(big['differs'].mean()).strip()}")

        L.append("  B6. Pathologies les plus concernées (part d'écart > tol, top 8) :")
        by = d.groupby("top", observed=True)["big"].mean().sort_values(ascending=False).head(8)
        for top, share in by.items():
            L.append(f"    {top} : {pct(share)}")
        L.append("  B7. Par classe d'âge (part d'écart > tol) :")
        by_age = d.groupby("age", observed=True)["big"].mean()
        L.append("    " + " | ".join(f"{a}={pct(v).strip()}" for a, v in by_age.items()))
    else:
        L.append("    aucun écart au-dessus de la tolérance.")

    text = "\n".join(L)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nRapport écrit : {OUT}")


if __name__ == "__main__":
    main()
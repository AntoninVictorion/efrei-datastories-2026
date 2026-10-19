"""Exploration ciblée du périmètre de l'étude (cancers, maladies neurologiques).

Objectifs : lever les points restés ouverts après `download_data.py inspect`.
  1. Lister les combinaisons exactes patho_niv1 / niv2 / niv3 / top du périmètre.
  2. Comprendre la géographie : formats de la colonne `dept`, rattachement région -> dept,
     présence éventuelle de lignes agrégées (région, France entière).
  3. Mesurer le masquage (secret statistique : Ntop vide) par pathologie et par année.
  4. Détecter les doublons sur la clé (annee, top, cla_age_5, sexe, region, dept).
  5. Vérifier que prev ≈ Ntop / Npop * 100.
  6. Compter les lignes agrégées « tous âges » (cla_age_5 = tsage) et « tous sexes » (sexe = 9).

Usage (depuis la racine du projet) :
    python scripts/explore_scope.py
Sortie : data/interim/scope_report.txt
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = ROOT / "data" / "raw" / "effectifs.csv"
REPORT_FILE = ROOT / "data" / "interim" / "scope_report.txt"

SEP = ";"                  # séparateur détecté par download_data.py inspect
CHUNK_ROWS = 500_000
SCOPE = ["Cancers", "Maladies neurologiques"]
KEY_COLS = ["annee", "top", "cla_age_5", "sexe", "region", "dept"]
DEPT_FORMAT = re.compile(r"^(\d{2}|2[AB]|\d{3})$")   # 01..95, 2A/2B, 971.. ; le reste est signalé


def _to_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.str.replace(",", ".", regex=False), errors="coerce")


def main() -> None:
    if not RAW_FILE.exists():
        sys.exit("CSV introuvable : lancer d'abord `python scripts/download_data.py download`.")
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    n_rows = 0
    combos: Counter = Counter()
    dept_counts: Counter = Counter()
    region_depts: dict[str, set] = defaultdict(set)
    masked: Counter = Counter()
    seen: Counter = Counter()
    aggregates: Counter = Counter()
    hashes: list[np.ndarray] = []
    n_checked = n_gap = 0
    max_gap = 0.0

    reader = pd.read_csv(RAW_FILE, sep=SEP, dtype=str, keep_default_na=False,
                         encoding="utf-8-sig", chunksize=CHUNK_ROWS)
    for chunk in reader:
        n_rows += len(chunk)

        # 4. doublons : on ne garde que des empreintes de la clé (peu de mémoire)
        hashes.append(pd.util.hash_pandas_object(chunk[KEY_COLS], index=False).to_numpy())

        # 2. géographie (sur tout le fichier)
        dept_counts.update(chunk["dept"].value_counts().to_dict())
        for region, dept in chunk[["region", "dept"]].drop_duplicates().itertuples(index=False):
            region_depts[region].add(dept)

        sc = chunk[chunk["patho_niv1"].isin(SCOPE)]
        if sc.empty:
            continue

        # 1. combinaisons de pathologies du périmètre
        grp = sc.groupby(["patho_niv1", "patho_niv2", "patho_niv3", "top"]).size()
        for key, n in grp.items():
            combos[key] += int(n)

        # 3. masquage par pathologie et année
        is_masked = sc["Ntop"] == ""
        for (niv1, annee), n in sc.groupby(["patho_niv1", "annee"]).size().items():
            seen[(niv1, annee)] += int(n)
        for (niv1, annee), n in sc[is_masked].groupby(["patho_niv1", "annee"]).size().items():
            masked[(niv1, annee)] += int(n)

        # 6. lignes agrégées
        flags = pd.DataFrame({"tous_ages": sc["cla_age_5"] == "tsage",
                              "tous_sexes": sc["sexe"] == "9"})
        for (a, s), n in flags.groupby(["tous_ages", "tous_sexes"]).size().items():
            aggregates[(bool(a), bool(s))] += int(n)

        # 5. cohérence prev ≈ Ntop / Npop * 100
        ok = sc[(sc["Ntop"] != "") & (sc["prev"] != "") & (sc["Npop"] != "")]
        if not ok.empty:
            ntop, npop, prev = _to_float(ok["Ntop"]), _to_float(ok["Npop"]), _to_float(ok["prev"])
            valid = (npop > 0) & ntop.notna() & prev.notna()
            gap = (prev[valid] - ntop[valid] / npop[valid] * 100).abs()
            n_checked += int(valid.sum())
            n_gap += int((gap > 0.05).sum())
            if len(gap):
                max_gap = max(max_gap, float(gap.max()))
        print(f"\r  {n_rows:,} lignes lues", end="", flush=True)
    print()

    all_hashes = np.concatenate(hashes)
    n_duplicates = len(all_hashes) - len(np.unique(all_hashes))

    L: list[str] = ["RAPPORT DE PÉRIMÈTRE - Pathologies : effectifs (CNAM)",
                    f"Lignes totales : {n_rows:,}", ""]

    L.append("== 1. Combinaisons du périmètre (niv1 | niv2 | niv3 | top : nb de lignes)")
    for (n1, n2, n3, top), n in sorted(combos.items()):
        L.append(f"  {n1} | {n2 or '-'} | {n3 or '-'} | {top} : {n:,}")
    L.append("")

    L.append("== 2. Géographie")
    odd = sorted(d for d in dept_counts if not DEPT_FORMAT.match(d))
    L.append(f"  Valeurs distinctes de dept : {len(dept_counts)}")
    L.append(f"  Valeurs hors format attendu (01..95, 2A/2B, 971..) : {odd if odd else 'aucune'}")
    for d in odd:
        L.append(f"    dept={d!r} : {dept_counts[d]:,} lignes")
    multi = sorted(d for d in dept_counts if sum(d in v for v in region_depts.values()) > 1)
    L.append(f"  dept rattachés à plusieurs régions : {multi if multi else 'aucun'}")
    L.append("  Région -> départements :")
    for region in sorted(region_depts):
        L.append(f"    {region} ({len(region_depts[region])}) : {sorted(region_depts[region])}")
    L.append("")

    L.append("== 3. Masquage (Ntop vide) par pathologie et année")
    for (niv1, annee) in sorted(seen):
        n, m = seen[(niv1, annee)], masked[(niv1, annee)]
        L.append(f"  {niv1} | {annee} : {m:,} / {n:,} = {m / n:.1%}")
    L.append("")

    L.append("== 4. Doublons sur la clé " + str(KEY_COLS))
    L.append(f"  Lignes en doublon : {n_duplicates:,}")
    L.append("")

    L.append("== 5. Cohérence prev ≈ Ntop / Npop * 100 (périmètre, lignes non masquées)")
    L.append(f"  Lignes vérifiées : {n_checked:,} | écart > 0,05 point : {n_gap:,} | écart max : {max_gap:.4f}")
    L.append("")

    L.append("== 6. Lignes agrégées du périmètre (tous_ages, tous_sexes : nb de lignes)")
    for (a, s), n in sorted(aggregates.items()):
        L.append(f"  tous_ages={a} | tous_sexes={s} : {n:,}")

    REPORT_FILE.write_text("\n".join(L), encoding="utf-8")
    print(f"Rapport écrit : {REPORT_FILE}")


if __name__ == "__main__":
    main()
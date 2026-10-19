"""Téléchargement (avec cache) et inspection du jeu de données CNAM
« Pathologies : effectif de patients par pathologie, sexe, classe d'âge et territoire ».

Source  : https://www.data.gouv.fr/datasets/pathologies-effectif-de-patients-par-pathologie-sexe-classe-dage-et-territoire-departement-region
Licence : ODbL (Caisse nationale de l'Assurance Maladie)

Usage (depuis la racine du projet) :
    python scripts/download_data.py download   # télécharge le CSV (~945 Mo) + échantillon
    python scripts/download_data.py inspect    # génère data/interim/schema_report.txt
    python scripts/download_data.py all        # les deux, dans l'ordre

Le CSV brut n'est JAMAIS versionné (voir .gitignore) : il est re-téléchargeable.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

URL = "https://www.data.gouv.fr/api/1/datasets/r/5f71ba43-afc8-43a0-b306-dafe29940f9c"

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
INTERIM_DIR = ROOT / "data" / "interim"
RAW_FILE = RAW_DIR / "effectifs.csv"
SAMPLE_FILE = RAW_DIR / "effectifs_sample.csv"
META_FILE = RAW_DIR / "effectifs.meta.txt"
REPORT_FILE = INTERIM_DIR / "schema_report.txt"

CHUNK_ROWS = 500_000      # lecture par morceaux : le fichier ne tient pas confortablement en RAM
MAX_DISTINCT = 100        # au-delà, une colonne est considérée à forte cardinalité
SAMPLE_LINES = 21         # en-tête + 20 lignes


def download(force: bool = False) -> None:
    """Télécharge le CSV en flux vers un fichier .part puis le renomme (cache)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and not force:
        print(f"[cache] {RAW_FILE} existe déjà ({RAW_FILE.stat().st_size / 1e6:.0f} Mo). "
              "Utiliser --force pour re-télécharger.")
        _write_sample()
        return

    part = RAW_FILE.with_suffix(".csv.part")
    sha = hashlib.sha256()
    done, start = 0, time.time()
    print(f"Téléchargement : {URL}")
    with requests.get(URL, stream=True, timeout=(10, 120),
                      headers={"User-Agent": "efrei-streamlit-student-project"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        with open(part, "wb") as f:
            for block in r.iter_content(chunk_size=1 << 20):
                f.write(block)
                sha.update(block)
                done += len(block)
                if total:
                    print(f"\r  {done / 1e6:7.0f} / {total / 1e6:.0f} Mo", end="", flush=True)
                else:
                    print(f"\r  {done / 1e6:7.0f} Mo", end="", flush=True)
    part.replace(RAW_FILE)
    print(f"\nTerminé en {time.time() - start:.0f} s.")

    META_FILE.write_text(
        f"url: {URL}\n"
        f"downloaded_on: {date.today().isoformat()}\n"
        f"size_bytes: {done}\n"
        f"sha256: {sha.hexdigest()}\n",
        encoding="utf-8",
    )
    print(f"Empreinte et date enregistrées dans {META_FILE}")
    _write_sample()


def _write_sample() -> None:
    """Copie les premières lignes du CSV (pour inspection rapide)."""
    with open(RAW_FILE, "r", encoding="utf-8-sig", errors="replace") as src, \
            open(SAMPLE_FILE, "w", encoding="utf-8") as dst:
        for i, line in enumerate(src):
            if i >= SAMPLE_LINES:
                break
            dst.write(line)
    print(f"Échantillon : {SAMPLE_FILE}")


def _detect_separator() -> str:
    with open(RAW_FILE, "r", encoding="utf-8-sig", errors="replace") as f:
        header = f.readline()
    try:
        return csv.Sniffer().sniff(header, delimiters=";,\t|").delimiter
    except csv.Error:
        return ";"


def inspect() -> None:
    """Parcourt le CSV par morceaux et écrit un rapport de schéma lisible."""
    if not RAW_FILE.exists():
        sys.exit("CSV introuvable : lancer d'abord `python scripts/download_data.py download`.")
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    sep = _detect_separator()
    n_rows = 0
    empty: dict[str, int] = {}
    ns: dict[str, int] = {}
    distinct: dict[str, set | None] = {}   # None = trop de valeurs distinctes
    columns: list[str] = []

    reader = pd.read_csv(RAW_FILE, sep=sep, dtype=str, keep_default_na=False,
                         encoding="utf-8-sig", chunksize=CHUNK_ROWS)
    for chunk in reader:
        if not columns:
            columns = list(chunk.columns)
            empty = dict.fromkeys(columns, 0)
            ns = dict.fromkeys(columns, 0)
            distinct = {c: set() for c in columns}
        n_rows += len(chunk)
        for c in columns:
            col = chunk[c]
            empty[c] += int((col == "").sum())
            ns[c] += int((col == "NS").sum())
            if distinct[c] is not None:
                distinct[c].update(col.unique())
                if len(distinct[c]) > MAX_DISTINCT:
                    distinct[c] = None
        print(f"\r  {n_rows:,} lignes lues", end="", flush=True)
    print()

    lines = [
        "RAPPORT DE SCHÉMA - Pathologies : effectifs (CNAM)",
        f"Fichier : {RAW_FILE.name}",
        f"Séparateur détecté : {sep!r}",
        f"Lignes : {n_rows:,}",
        f"Colonnes ({len(columns)}) : {columns}",
        "",
    ]
    for c in columns:
        values = distinct[c]
        lines.append(f"--- {c}")
        lines.append(f"    vides : {empty[c]:,} | 'NS' : {ns[c]:,}")
        if values is None:
            lines.append(f"    valeurs distinctes : > {MAX_DISTINCT} (forte cardinalité)")
        else:
            ordered = sorted(values)
            lines.append(f"    valeurs distinctes : {len(ordered)}")
            shown = ordered if len(ordered) <= 60 else ordered[:15] + ["..."]
            lines.append(f"    valeurs : {shown}")
        lines.append("")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rapport écrit : {REPORT_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["download", "inspect", "all"])
    parser.add_argument("--force", action="store_true", help="re-télécharger même si le cache existe")
    args = parser.parse_args()

    if args.command in ("download", "all"):
        download(force=args.force)
    if args.command in ("inspect", "all"):
        inspect()


if __name__ == "__main__":
    main()
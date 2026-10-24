# Cancers and dementia in France: where does the burden exceed what age explains?

Data-storytelling dashboard built with **Streamlit** for the #EFREIDataStories2026 project.

- **Deployed app:** https://health-priorities-france.streamlit.app
- **Demo video (2-4 min):** https://youtu.be/Xwz9CC0PZrM
- **Storyboard:** [docs/storyboard.md](https://github.com/AntoninVictorion/efrei-datastories-2026/blob/main/docs/storyboard.md)
- **Author:** Antonin VICTORION, student n° 20231614, group BIA

## The question

> As a regional health authority (ARS), which territories should we look at first for cancers and dementia, given age, the number of patients concerned, and the trend?

**Audience:** a regional health decision-maker, or an informed citizen.

**Narrative:** hook (cancer up, dementia down, while the population ages), context (age drives prevalence), key insights (where, which regions, is it changing, where first), implications and next steps. In the demo video, lung cancer and the département of Hérault serve as the guiding case.

## What the app shows

| # | Section | Question it answers |
|---|---|---|
| 1 | Paradox | Cancer +9.3%, dementia -7.1% since 2015: is it real? |
| 2 | Age | Why raw prevalence misleads |
| 3 | One department | Raw prevalence vs age-adjusted index (4 key figures vs France) |
| 4 | Map | Where is the burden above what age explains? |
| 5 | Regions | Which regions stand out, and how sure are we? |
| 6 | Gap over time | Are regional gaps growing or shrinking? |
| 7 | Priorities | Intensity (index) vs volume (patients above expected) |
| 8 | Takeaways | What to do next |
| - | Data quality | Missing values, validation checks, limitations |

**Interactions:** sidebar filters for condition, sex, period and department (they apply from section 3); hover tooltips on every chart.

## Data

- **Source:** Caisse nationale de l'Assurance Maladie (CNAM), *Pathologies: number of patients by condition, sex, age group and territory*, on [data.gouv.fr](https://www.data.gouv.fr/datasets/pathologies-effectif-de-patients-par-pathologie-sexe-classe-dage-et-territoire-departement-region). Years 2015-2024, updated 6 July 2026.
- **Licence:** ODbL. A database derived from it must be shared under the same conditions, with the source cited.
- **Scope:** cancers and neurological diseases (including dementia), 1.66 million rows, 101 departments, 18 regions and France.
- **Map outlines:** [gregoiredavid/france-geojson](https://github.com/gregoiredavid/france-geojson), derived from IGN Admin Express, French Open Licence (Etalab).
- The raw file (945 MB) is **not** in the repository. It is downloaded by a script, with caching and a SHA-256 checksum.

## Run the app

The processed tables are versioned in `data/processed/`, so the app runs without downloading the raw file.

```bash
conda env create -f environment-dev.yml
conda activate efrei-dashboard
streamlit run app.py
```

Without conda: Python 3.11, then `pip install -r requirements.txt`, then `streamlit run app.py`.

### Environment files

- `requirements.txt`: pinned dependencies used by the deployed app (pip, Streamlit Community Cloud).
- `environment-dev.yml`: conda environment for local development (conda-forge, Python 3.11).

## Rebuild the data from scratch

Run from the project root. Each step produces the input of the next one.

| Step | Command | Produces |
|---|---|---|
| Download (cached) | `python scripts/download_data.py all` | `data/raw/effectifs.csv`, checksum, schema report |
| Explore the scope | `python scripts/explore_scope.py` | `data/interim/scope_report.txt` |
| Clean fact table + quality checks | `python scripts/build_facts.py` | `data/processed/facts.parquet`, `quality_report.json` |
| Diagnostics | `python scripts/diagnose_data.py` | `data/processed/diagnostic.txt` |
| App tables | `python scripts/prep.py` | `trend_national`, `trend_region`, `profile_age_sex`, `index_territoire` (parquet) |

## Project structure

```
app.py                  the story, section by section
sections/quality.py     data quality section (reads quality_report.json)
utils/viz.py            chart functions (Plotly)
utils/story.py          sentences that link the charts (numbers come from the data)
utils/labels.py         English names of conditions and sexes
scripts/                download, cleaning, checks, app tables
data/processed/         versioned parquet tables and quality report
data/geo/               department outlines
docs/storyboard.md      storyboard
```

## Method in short

- **Prevalence:** share of insured people treated for a condition. We display the **published CNAM prevalence**.
- **Comparative index** (indirect standardisation): observed cases divided by the cases expected if the territory had the national prevalence at each age. 1.2 means 20% more cases than expected. 95% confidence interval: Byar method.
- **Threshold:** gaps within +/-10% are shown as neutral. Statistical significance is not used, because with very large counts almost every gap is significant.
- **Patients above expected:** observed minus expected cases, used as a measure of volume next to the index (intensity).
- **No total is recomputed:** each level uses its own published row.
- **Conditions are never summed:** a patient can have several.

## Data quality

The full report is in the app. Key points:

- Counts below 11 are hidden by the publisher (35% of department-by-age rows), so department age views are limited to ages 50-89.
- Patient counts are rounded to 10; the published prevalence is used to avoid rounding effects.
- France vs sum of regions differs by at most 1.7%; regional vs sum of departments by at most 2.1%.
- Active + under surveillance equals the category exactly for the five cancer types.
- No duplicated rows on the key (year, condition, sex, age, level, region, department).

## Limitations

- Prevalence is **detected from reimbursed care**, not a clinical diagnosis. The reference population is insured people who used the health system, so it may differ from the whole resident population.
- Prevalence mixes new cases and survival.
- Trend curves use raw prevalence, not age-standardised: a rise can partly reflect ageing. Only the comparative index is age-adjusted.
- The index compares each territory with France, not two territories with each other.
- No causal reading: screening, access to care, social conditions and coding practices are hypotheses, not findings.
- The dementia decline since 2015 may be partly artificial. Anti-Alzheimer drugs stopped being reimbursed in August 2018; if the CNAM algorithm uses them, this could create a break. This is an **unverified hypothesis**.
- Overseas departments have very low indices and are shown apart from the map.

## Performance

- Pre-aggregated parquet tables are built once by `scripts/prep.py`; the app never reads the raw file.
- Data loading uses `st.cache_data`.

## Accessibility

- Every chart has labelled axes with units, a title and a plain-language description below it.
- Colours: a diverging blue-orange scale with a neutral grey band; colour is never the only cue (values appear in tooltips and in generated sentences).

## Reproducibility

- Dependencies are pinned in `requirements.txt`; local environment in `environment-dev.yml`.
- The download script caches the file and records its SHA-256 checksum.
- No sampling or randomness: results are deterministic.

## Use of AI

An AI assistant (Claude) was used for guidance and code review. The code was shown for review before being added to the repository; all code and text are understood and validated by the author.
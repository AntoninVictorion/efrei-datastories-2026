# Cancers and dementia in France: where does the burden exceed what age explains?

Data-storytelling dashboard built with **Streamlit** for the #EFREIDataStories2026 project.

- **Deployed app:** [add the URL after deployment]
- **Demo video (2-4 min):** [add the link]
- **Storyboard:** [add the link]
- **Author:** [First name LAST NAME], student n° [number], group [group]

## The question

> As a regional health authority (ARS), which territories should we look at first for cancers and dementia, given age, the number of patients concerned, and the trend?

**Audience:** a regional health decision-maker, or an informed citizen.

**Narrative:** hook (cancer up, dementia down, while the population ages), context (age drives prevalence), key insights (where, which regions, is it changing, where first), implications and next steps.

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
conda env create -f environment.yml
conda activate efrei-dashboard
streamlit run app.py
```

Without conda: Python 3.11, then `pip install -r requirements.txt`.

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
```

## Method in short

- **Prevalence:** share of insured people treated for a condition. We display the **published CNAM prevalence**.
- **Comparative index** (indirect standardisation): observed cases divided by the cases expected if the territory had the national prevalence at each age. 1.2 means 20% more cases than expected. 95% confidence interval: Byar method.
- **Threshold:** gaps within +/-10% are shown as neutral. Statistical significance is not used, because with very large counts almost every gap is significant.
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

- Prevalence is **detected from reimbursed care**, not a clinical diagnosis. The reference population is insured people who

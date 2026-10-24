# Storyboard: Cancers and dementia in France

**Author:** Antonin Victorion (20231614, BIA)
**Audience:** a regional health authority (ARS) decision-maker, or an informed citizen.
**Guiding question:** As a regional health authority (ARS), which territories should we look at first
for cancers and dementia, given age, the number of patients concerned, and the trend?
**Thread:** lung cancer, with Hérault (34) as the guiding case.
**Source:** CNAM, "Pathologies: number of patients by condition, sex, age group and territory",
data.gouv.fr, ODbL licence, 2015-2024.

## Narrative arc

| # | Chapter | Role | Headline | Visual and interaction | Takeaway |
|---|---|---|---|---|---|
| 1 | Paradox | Hook | Cancers rise (+9%) while dementia falls (-7%), even though the population ages. | Base-100 lines, national, 2018 marker. Not affected by filters. | Something unexpected is happening: read the numbers with care. |
| 2 | Age | Context | Prevalence is driven by age, so raw rates mislead. | Age profile by condition and sex. | Territories must be compared at equal age structure. |
| 3 | Hérault | Context | Hérault's raw lung cancer prevalence is 28% above France and grew faster since 2015 (+44% vs +36%). | 4 KPIs, generated sentence, base-100 curve vs France. Filter: department. | One territory, read against the national curve. Raw rate still mixes age and burden. |
| 4 | Map | Insight | Once age is accounted for, Corsica and the Ardennes show the highest intensity. | Choropleth of the comparative index, +/-10% neutral band, overseas apart. Hover for details. | Where the gaps are. |
| 5 | Regions | Insight | Regional gaps, with their uncertainty. | Dot chart with 95% confidence intervals. | How sure we are. |
| 6 | Gaps over time | Insight | Northern and eastern regions move toward the average, while Corsica and Occitanie move away. | Dumbbell, first vs last year. | The trend matters, not only the level. |
| 7 | Priorities | Implication | Intensity and volume point to different places: Corsica for intensity, Hérault for volume (+877 patients above expected, index 1.25). | Scatter: patients above expected vs index. | Two kinds of priority, both needed. |
| 8 | Takeaways | Next steps | A gap is a place to investigate, not a diagnosis of need. | Static text. | Actionable, no causal claim. |
| + | Data quality | Transparency | Masking, rounding, reference population, overseas gaps. | Masking chart, 8 validation checks, limits. | How far to trust the numbers. |

## Recording settings

Lung cancer, both sexes, 2015-2024, Hérault (34). Transition from chapter 1: "Cancers overall are rising; let's zoom on lung cancer."

## Limits stated in the app and the video

- Prevalence is not age-standardised in the trend curves: a rise can reflect ageing.
- Prevalence mixes new cases and survival.
- The population is insured people who used care in the year; detection relies on reimbursed care, not clinical diagnoses.
- Counts below 11 are masked, others are rounded to 10.
- No causal reading: screening, access to care and coding practices are hypotheses.
- Overseas departments are shown apart (very low index) and absent from the regional chart.
- The 2018 break concerns dementia only and is an unverified hypothesis.
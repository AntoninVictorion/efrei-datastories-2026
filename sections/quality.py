"""Data quality and limitations section, fed by data/processed/quality_report.json."""
import pandas as pd
import plotly.express as px
import streamlit as st


def show_quality(report):
    st.header("Data quality and limitations")
    src, res, mask = report["source"], report["resume"], report["masquage"]

    # --- Source and size
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows analysed", f"{res['lignes_perimetre']:,}")
    c2.metric("Conditions", res["pathologies_top"])
    c3.metric("Years", f"{res['annees'][0]}-{res['annees'][1]}")
    c4.metric("Raw file", f"{int(src['size_bytes']) / 1e6:,.0f} MB")
    st.caption(f"Downloaded on {src['downloaded_on']} from data.gouv.fr (ODbL licence). "
               f"SHA-256: `{src['sha256'][:16]}...` (the download script checks it).")

    # --- Missing values: statistical confidentiality
    st.subheader("Missing values: statistical confidentiality")
    st.markdown("Counts below 11 patients are hidden by the publisher. They are **left empty, never replaced**.")
    rows = [{"Level": k.split("|")[0].replace("dept", "Department").replace("region", "Region").replace("france", "France"),
             "Detail": "All ages" if k.endswith("True") else "By age group",
             "Rows": v["lignes"], "Masked (%)": round(v["part"] * 100, 1)}
            for k, v in mask["par_niveau_geo_et_tous_ages"].items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True)

    by_age = pd.Series(mask["departements_par_classe_age"]).rename_axis("Age group").reset_index(name="Masked")
    by_age["Age group"] = by_age["Age group"].str.replace("et+", "+", regex=False)
    fig = px.bar(by_age, x="Age group", y="Masked", title="Share of masked rows by age group (departments)",
                 labels={"Masked": "Share of masked rows"})
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig)
    st.info("Department-level age views are therefore limited to ages 50-89, where at most about 12% of rows "
            "are masked. At department level, all-ages figures are masked in only 0.3% of rows.")

    # --- Validation checks
    st.subheader("Validation checks")
    prev = report["prevalence_cnam_vs_recalculee"]["groupes"]
    geo = report["geographie"]
    ratios = [v["france_sur_somme_des_regions_par_annee"] for v in geo.values()]
    first, last = min(res["annees"]), max(res["annees"])
    regional = max(v["total_regional_sur_somme_departements"]["max"] for v in geo.values())
    surveillance = max(r for d in report["categorie_vs_actif_plus_surveillance"].values() for r in d.values())
    dept_gap = [v["part_ecart_sup_tolerance"] for k, v in prev.items()
                if k.startswith("tous_ages=False") and k.endswith("dept")]
    n_dup = report.get("doublons_et_manquants", {}).get("lignes_dupliquees")
    checks = [
        ("Published vs recomputed prevalence (all ages)",
         f"Largest gap: {max(v['ecart_abs_max'] for k, v in prev.items() if k.startswith('tous_ages=True')):.3f} point",
         "Matches. We display the published CNAM prevalence."),
        ("Published vs recomputed prevalence (by age, departments)",
         f"{min(dept_gap):.0%}-{max(dept_gap):.0%} of rows differ beyond tolerance",
         "Explained by counts rounded to 10 in small populations."),
        ("France total vs sum of regions",
         f"Up to +{(max(r[str(first)] for r in ratios) - 1) * 100:.1f}% in {first}, "
         f"+{(max(r[str(last)] for r in ratios) - 1) * 100:.1f}% in {last}",
         "Patients without a region. No total is ever recomputed."),
        ("Regional total vs sum of departments", f"At most +{(regional - 1) * 100:.1f}%", "Consistent."),
        ("Active + under surveillance = category", f"Ratio {surveillance:.4f} at most", "Exact: they can be stacked."),
        ("Population denominators",
         f"{report['population_npop']['part_cellules_npop_differant_selon_pathologie']:.0%} of cells differ by condition",
         "Breast and prostate use a sex-specific population. We use each row's own denominator."),
        ("Duplicated rows (year, condition, sex, age, level, region, department)",
         "n/a (run build_facts.py again)" if n_dup is None else f"{n_dup} found",
         "Nothing to remove." if n_dup == 0 else ""),
        ("Non-numeric values", f"{len(res['valeurs_non_numeriques_ignorees'])} found", "None to clean."),
    ]
    st.table(pd.DataFrame(checks, columns=["Check", "Result", "What we do"]).set_index("Check"))

    # --- Limits
    st.subheader("Limitations")
    france_age = mask["par_niveau_geo_et_tous_ages"]["france|tous_ages=False"]["part"]
    st.markdown(
        "- **Detected, not diagnosed**: prevalence is inferred from reimbursed care (CNAM algorithms). "
        "The reference population is insured people who used healthcare during the year.\n"
        "- **Rounded counts**: patient counts are rounded to the nearest 10, so small territories are noisy.\n"
        "- **The index compares each territory with France**, not two territories with each other. "
        "It shows a gap, not a cause (access to diagnosis, social conditions and coding practices are hypotheses).\n"
        "- **A +/-10% threshold** is used instead of statistical significance: with very large counts, almost "
        "every gap is significant (87 of 101 departments for dementia).\n"
        "- **Dementia trend**: the fall may partly reflect the end of anti-Alzheimer drug reimbursement "
        "in August 2018. This is a hypothesis we did not verify.\n"
        f"- **Index gaps**: {france_age:.1%} of national age-specific cells are masked, so the index is "
        "not computed for those cells.\n"
        "- **Two prevalence sources**: the department curve uses counts / population, France uses the published "
        "CNAM prevalence. Differences are negligible at all ages (see checks).")
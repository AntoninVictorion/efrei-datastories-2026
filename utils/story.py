"""Short sentences that link the charts into one story. Numbers come from the data."""
import pandas as pd

AGE_TEXT = ("Prevalence is close to zero before 50 and climbs steeply after 70. A department with more elderly "
            "residents will therefore have more cases even if nothing else differs. To compare territories fairly, "
            "we compare each one with the cases **expected for its age structure**: this is the *comparative index* "
            "(1.2 = 20% more cases than expected).")


def hook_text(y0, y1, cancers, dementia):
    return (f"Between {y0} and {y1}, cancer prevalence changed by **{cancers:+.1f}%** and dementia prevalence by "
            f"**{dementia:+.1f}%**, although the population is ageing. Is this real? And do some territories carry "
            "a heavier burden than their age structure explains?")


def kpi_text(name, gap, index):
    """Links raw prevalence (key figure 1) to the age-adjusted index (key figure 3)."""
    if pd.isna(gap) or pd.isna(index):
        return ""
    raw = "higher" if gap > 0 else "lower"
    adj = "above" if index > 1.1 else "below" if index < 0.9 else "in line with"
    return (f"In {name}, raw prevalence is {abs(gap):.0f}% {raw} than in France. Once age is taken into account, "
            f"the department is **{adj}** what is expected (index {index:.2f}).")


def map_text(metro, names):
    """metro: mainland departments for one year, with an 'indice' column."""
    metro = metro.dropna(subset=["indice"])
    n_above, n_below = (metro["indice"] > 1.1).sum(), (metro["indice"] < 0.9).sum()
    text = (f"Among {len(metro)} mainland departments, **{n_above}** are more than 10% above the expected level "
            f"and **{n_below}** more than 10% below.")
    top = metro[metro["indice"] > 1.1].nlargest(3, "indice")
    if len(top):
        text += " Highest: " + ", ".join(f"{names[d]} ({i:.2f})" for d, i in zip(top["dept"], top["indice"])) + "."
    return text


def region_text(reg):
    """reg: one row per region with 'region_nom' and 'indice'."""
    up = reg[reg["indice"] > 1.1].sort_values("indice", ascending=False)["region_nom"]
    down = reg[reg["indice"] < 0.9].sort_values("indice")["region_nom"]
    text = ("More than 10% above expected: " + ", ".join(up) + "." if len(up)
            else "No region is more than 10% above the expected level.")
    if len(down):
        text += " More than 10% below: " + ", ".join(down) + "."
    return text


def gap_text(df, y0, y1):
    """df: region rows for the two years. A region 'moves away' when its index gets further from 1."""
    wide = df.pivot(index="region_nom", columns="annee", values="indice").dropna()
    change = (wide[y1] - 1).abs() - (wide[y0] - 1).abs()
    return (f"Since {y0}, **{(change > 0.02).sum()}** regions moved further away from the national level and "
            f"**{(change < -0.02).sum()}** moved closer (changes under 0.02 are ignored).")


def priority_text(df, names):
    """df: departments with 'excess' = observed - expected patients."""
    top = df.nlargest(3, "excess")
    items = ", ".join(f"{names[d]} (+{e:,.0f} patients, index {i:.2f})"
                      for d, e, i in zip(top["dept"], top["excess"], top["indice"]))
    return f"The largest numbers of patients above the age-expected level are in: {items}."
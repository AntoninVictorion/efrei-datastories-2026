import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

OVERSEAS = ["971", "972", "973", "974", "976"]   # not in the GeoJSON: shown apart
# Diverging scale on 0.7-1.3: blue = below France, grey = within +/-10%, orange = above
SCALE = [[0, "#1c4f94"], [0.333, "#a9c7ee"], [0.334, "#dcdbd5"],
         [0.666, "#dcdbd5"], [0.667, "#f6b497"], [1, "#b8431a"]]


def to_base_100(df):
    """Rescale prevalence so the first year equals 100."""
    return df["prevalence"] / df["prevalence"].iloc[0] * 100


def trend_chart(france, territory, territory_name, title, france_name="France"):
    """Two curves rebased to 100 in the first year (a territory vs France, or one condition vs another)."""
    fig = go.Figure()
    for name, df, color in [(france_name, france, "#52514e"),
                            (territory_name, territory, "#2a78d6")]:
        fig.add_scatter(x=df["annee"], y=to_base_100(df), name=name,
                        mode="lines+markers", line=dict(color=color, width=3))

    fig.add_hline(y=100, line_color="lightgrey")
    fig.add_vrect(x0=2019.5, x1=2020.5, fillcolor="grey", opacity=0.15,
                  annotation_text="Covid-19")
    fig.update_layout(title=title, xaxis_title="Year", template="plotly_white",
                      yaxis_title=f"Prevalence (index, {france['annee'].iloc[0]} = 100)")
    return fig


def index_map(df, geojson, names, title):
    """Map of the comparative index by department (df: one row per department)."""
    df = df[~df["dept"].isin(OVERSEAS)].copy()
    df["name"] = df["dept"].map(names)
    fig = px.choropleth(
        df, geojson=geojson, locations="dept", featureidkey="properties.code",
        color="indice", range_color=(0.7, 1.3), color_continuous_scale=SCALE,
        hover_name="name", hover_data={"dept": False, "indice": ":.2f",
                                       "ic_bas": ":.2f", "ic_haut": ":.2f"},
        labels={"indice": "Index", "ic_bas": "95% CI low", "ic_haut": "95% CI high"},
        title=title)
    fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
    return fig


def region_chart(df, title):
    """Dot plot of the comparative index by region, with 95% confidence intervals."""
    df = df.sort_values("indice")
    fig = px.scatter(df, x="indice", y="region_nom", title=title,
                     error_x=df["ic_haut"] - df["indice"],
                     error_x_minus=df["indice"] - df["ic_bas"],
                     labels={"indice": "Comparative index (1 = France)", "region_nom": ""},
                     hover_data={"indice": ":.2f"})
    fig.add_vrect(x0=0.9, x1=1.1, fillcolor="grey", opacity=0.2, line_width=0)  # +/-10% band
    fig.add_vline(x=1)                                                          # France = 1
    fig.update_xaxes(range=[0.6, 1.5])
    fig.update_yaxes(categoryorder="array", categoryarray=df["region_nom"], dtick=1)  # one label per row
    fig.update_layout(height=550)
    return fig

def age_chart(df, title):
    """Prevalence by age: one panel per condition (own y axis), men vs women."""
    fig = px.line(df, x="age_mid", y="prevalence", color="sex", facet_col="condition",
                  markers=True, title=title,
                  labels={"age_mid": "Age (years)", "prevalence": "Prevalence (%)",
                          "sex": "", "condition": ""},
                  color_discrete_map={"Men": "#2a78d6", "Women": "#eb6834"},
                  category_orders={"condition": ["Cancers", "Dementia", "Neurological diseases"]},)
    fig.update_yaxes(matches=None, showticklabels=True)   # each panel keeps its own scale
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))  # "=Cancers" -> "Cancers"
    return fig


def gap_chart(df, y0, y1, title):
    """Dumbbell: comparative index of each region in the first and in the last year."""
    df = df.dropna(subset=["indice"])
    order = df[df["annee"] == y1].sort_values("indice")["region_nom"]
    fig = go.Figure()
    for _, g in df.groupby("region_nom"):                      # one grey segment per region
        fig.add_scatter(x=g["indice"], y=g["region_nom"], mode="lines",
                        line_color="lightgrey", showlegend=False, hoverinfo="skip")
    for year, color in [(y0, "#9aa0a6"), (y1, "#2a78d6")]:
        g = df[df["annee"] == year]
        fig.add_scatter(x=g["indice"], y=g["region_nom"], mode="markers", name=str(year),
                        marker=dict(size=11, color=color))
    fig.add_vrect(x0=0.9, x1=1.1, fillcolor="grey", opacity=0.2, line_width=0)
    fig.add_vline(x=1)
    fig.update_xaxes(range=[0.6, 1.5], title="Comparative index (1 = France)")
    fig.update_yaxes(categoryorder="array", categoryarray=order, dtick=1)
    fig.update_layout(title=title, height=550, template="plotly_white")
    return fig


def with_excess(df):
    """Add 'excess' = patients observed minus patients expected from the age structure."""
    return df.assign(excess=df["effectif_observe"] - df["effectif_attendu"])


def priority_chart(df, names, title):
    """One dot per department: intensity (index) against volume (patients above expected)."""
    df = df.copy()
    df["name"] = df["dept"].map(names)
    df["group"] = pd.cut(df["indice"], [0, 0.9, 1.1, 9], right=False,
                         labels=["Below expected", "Within ±10%", "Above expected"])
    df["tag"] = df["name"].where(df["excess"].rank(ascending=False) <= 5, "")   # label the 5 largest
    fig = px.scatter(df, x="indice", y="excess", color="group", text="tag", hover_name="name",
                     color_discrete_map={"Below expected": "#2a78d6", "Within ±10%": "#9aa0a6",
                                         "Above expected": "#eb6834"},
                     hover_data={"indice": ":.2f", "excess": ":,.0f", "group": False, "tag": False},
                     labels={"indice": "Comparative index (1 = France)",
                             "excess": "Patients above (+) or below (-) expected", "group": ""},
                     title=title)
    fig.add_vline(x=1)
    fig.add_hline(y=0)
    fig.update_traces(textposition="top center")
    fig.update_xaxes(range=[0.6, 1.5])
    return fig
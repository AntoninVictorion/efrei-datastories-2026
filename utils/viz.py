import plotly.graph_objects as go


def to_base_100(df):
    """Rescale prevalence so the first year equals 100."""
    return df["prevalence"] / df["prevalence"].iloc[0] * 100


def trend_chart(france, territory, territory_name, title):
    fig = go.Figure()
    for name, df, color in [("France", france, "#52514e"),
                            (territory_name, territory, "#2a78d6")]:
        fig.add_scatter(x=df["annee"], y=to_base_100(df), name=name,
                        mode="lines+markers", line=dict(color=color, width=3))

    fig.add_hline(y=100, line_color="lightgrey")
    fig.add_vrect(x0=2019.5, x1=2020.5, fillcolor="grey", opacity=0.15,
                  annotation_text="Covid-19")
    fig.update_layout(title=title, xaxis_title="Year", template="plotly_white",
                      yaxis_title=f"Prevalence (index, {france['annee'].iloc[0]} = 100)")
    return fig
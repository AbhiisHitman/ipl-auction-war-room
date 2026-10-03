"""Static charts for the deck / README (outputs/charts/*.png).

Palette: reference data-viz palette (light mode). Status colours are reserved
for the Green/Amber/Red coverage matrix and always carry a text label too.

    python -m src.charts
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .config import CHARTS_DIR, PROCESSED_DIR, ensure_dirs
from .economics import default_inputs, pnl
from .squad import ROLES
from .teams import active_codes

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e1"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
DIV_COOL, DIV_WARM, DIV_MID = "#2a78d6", "#e34948", "#b5b3ad"
STATUS = {"Green": "#0ca30c", "Amber": "#fab219", "Red": "#d03b3b"}
FONT = dict(family="Inter, Helvetica, Arial, sans-serif", size=13, color=INK)


def _layout(fig: go.Figure, title: str, subtitle: str, w: int = 1200, h: int = 700) -> go.Figure:
    fig.update_layout(
        title=dict(text=f"<b>{title}</b><br><span style='font-size:13px;color:{INK_2}'>{subtitle}</span>",
                   x=0.01, xanchor="left", font=dict(size=19, color=INK)),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font=FONT, width=w, height=h,
        margin=dict(l=70, r=40, t=100, b=60),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, tickfont=dict(color=INK_2))
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, tickfont=dict(color=INK_2))
    return fig


def market_scatter() -> str:
    """Impact vs auction price; under/overpriced vs model fair value highlighted."""
    t = pd.read_csv(PROCESSED_DIR / "market_training.csv")
    t["price_cr"] = t["sold_price_lakh"] / 100
    t["band"] = pd.cut(t["mispricing_pct"], [-10, -0.5, 1.0, 100],
                       labels=["Overpriced (paid >2x fair value)", "Near fair value", "Underpriced (paid <50% of fair value)"])
    colors = {"Overpriced (paid >2x fair value)": DIV_WARM, "Near fair value": DIV_MID,
              "Underpriced (paid <50% of fair value)": DIV_COOL}
    fig = go.Figure()
    for band in ["Near fair value", "Overpriced (paid >2x fair value)", "Underpriced (paid <50% of fair value)"]:
        d = t[t["band"] == band]
        fig.add_trace(go.Scatter(
            x=d["impact"], y=d["price_cr"], mode="markers", name=f"{band} (n={len(d)})",
            marker=dict(size=9, color=colors[band], line=dict(color=SURFACE, width=2),
                        opacity=0.55 if band == "Near fair value" else 0.9)))
    # Label a few extremes on each side
    for d in (t.nsmallest(4, "mispricing_pct"), t.nlargest(3, "mispricing_pct")):
        for _, r in d.iterrows():
            # annotations on a log axis take log10 coordinates
            fig.add_annotation(x=r["impact"], y=np.log10(r["price_cr"]), text=f"{r['player_name']} '{str(r['season'])[2:]}",
                               showarrow=False, yshift=12, font=dict(size=11, color=INK_2))
    fig.update_yaxes(type="log", title="Auction price (INR crore, log scale)")
    fig.update_xaxes(title="Impact Score at time of auction (runs/match vs league average)")
    fig.update_layout(legend=dict(orientation="h", y=-0.15, x=0))
    _layout(fig, "Price tracks reputation more than output",
            "Sold players 2022-2026 auctions; fair value = typical price for the same impact, cap status and year")
    path = CHARTS_DIR / "market_impact_vs_price.png"
    fig.write_image(path, scale=2)
    return str(path)


def coverage_matrix() -> str:
    cov = pd.read_csv(PROCESSED_DIR / "coverage.csv")
    teams = active_codes()
    z = {"Green": 2, "Amber": 1, "Red": 0}
    grid = cov.pivot(index="team", columns="role", values="status").reindex(index=teams, columns=ROLES)
    fig = go.Figure(go.Heatmap(
        z=grid.replace(z).values.astype(float), x=ROLES, y=teams, zmin=0, zmax=2,
        colorscale=[[0, STATUS["Red"]], [0.5, STATUS["Amber"]], [1, STATUS["Green"]]],
        showscale=False, xgap=3, ygap=3,
        text=grid.replace({"Green": "G", "Amber": "A", "Red": "R"}).values,
        texttemplate="<b>%{text}</b>", textfont=dict(color=INK, size=14)))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top", showgrid=False, tickangle=0, tickfont=dict(size=11),
                     ticktext=[r.replace(" ", "<br>") for r in ROLES], tickvals=ROLES)
    _layout(fig, "Every squad has a different gap to fill",
            "Role coverage of the 2026 squads: G = k-th best player is starter quality (league top 10k), "
            "A = top 15k, R = below that or too few players", h=640)
    fig.update_layout(margin=dict(t=160))
    path = CHARTS_DIR / "squad_gap_matrix_all_teams.png"
    fig.write_image(path, scale=2)
    return str(path)


def top_impact() -> str:
    p = pd.read_csv(PROCESSED_DIR / "players.csv")
    d = p[p["has_impact"]].nlargest(20, "impact").iloc[::-1]
    labels = [f"{n} ({t if isinstance(t, str) else 'unsigned'})" for n, t in zip(d["display_name"], d["current_team"])]
    fig = go.Figure(go.Bar(x=d["impact"], y=labels, orientation="h", marker=dict(color=BLUE, cornerradius=4),
                           text=d["impact"].round(1), textposition="outside", textfont=dict(color=INK_2)))
    fig.update_xaxes(title="Impact Score (runs/match vs league average, 2024-26 weighted)")
    _layout(fig, "Top-20 players by Impact Score going into IPL 2027",
            "Batting + bowling runs added per match vs an average player, shrunk for small samples", h=760)
    fig.update_layout(margin=dict(l=260))
    path = CHARTS_DIR / "top20_impact.png"
    fig.write_image(path, scale=2)
    return str(path)


def revenue_mix(team: str = "CSK") -> str:
    homes = pd.read_csv(PROCESSED_DIR / "home_venues.csv").set_index("team")["venue"]
    inp = default_inputs(team, homes[team])
    groups = {"Central media rights": ["Central media rights share"],
              "Central sponsorship": ["Central sponsorship share"],
              "Team-generated (sponsors, tickets, merch)": ["Team sponsorships", "Ticketing (home matches)", "Merchandise"],
              "Prize money": ["Prize money"]}
    colors = [BLUE, ORANGE, AQUA, YELLOW]
    labels = {"missed_playoffs": "Missed playoffs", "made_playoffs": "Made playoffs", "won_title": "Won title"}
    fig = go.Figure()
    tables = {s: pnl(inp, s).set_index("line")["value_cr"] for s in labels}
    for (g, lines), col in zip(groups.items(), colors):
        fig.add_trace(go.Bar(name=g, y=list(labels.values()), x=[tables[s][lines].sum() for s in labels],
                             orientation="h", marker=dict(color=col, line=dict(color=SURFACE, width=2))))
    for s, lab in labels.items():
        fig.add_annotation(x=tables[s]["Total revenue"], y=lab, text=f"Rs {tables[s]['Total revenue']:.0f} cr",
                           showarrow=False, xanchor="left", xshift=6, font=dict(color=INK))
    mix = tables["missed_playoffs"]["Central (fixed) share of revenue"]
    fig.update_layout(barmode="stack", legend=dict(orientation="h", y=-0.2, x=0, traceorder="normal"))
    fig.update_xaxes(title="Revenue, INR crore per season", range=[0, tables["won_title"]["Total revenue"] * 1.15])
    _layout(fig, f"{mix:.0%} of revenue is fixed central income; winning moves only the thin slice on top",
            f"{team} revenue by performance scenario (model in outputs/excel/franchise_model.xlsx)", h=520)
    path = CHARTS_DIR / f"revenue_mix_{team}.png"
    fig.write_image(path, scale=2)
    return str(path)


def main() -> None:
    ensure_dirs()
    for f in (market_scatter, coverage_matrix, top_impact, revenue_mix):
        print(f())


if __name__ == "__main__":
    main()

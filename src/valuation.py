"""Impact Score: runs a player adds per match versus a league-average player.

Batting impact = sum(runs off ball - phase baseline)
                 - (dismissals - expected dismissals) x wicket_value[phase]
Bowling impact = sum(phase baseline - runs conceded)
                 + (wickets - expected wickets) x wicket_value[phase]

"Expected" = balls x league-average dismissal rate for that season and phase,
so a league-average batter and bowler both score exactly 0.

* phase baseline = league runs per ball in that season and phase
* wicket_value  = runs a wicket costs the batting side in that phase, measured
                  from a run-expectancy table (see wicket_values()).
Per-season score = (batting + bowling) per match, shrunk for small samples,
then combined across the last 3 seasons with recency weights.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import valuation_params

PHASES = ["Powerplay", "Middle", "Death"]


# --------------------------------------------------------------------------
# Baselines and wicket values
# --------------------------------------------------------------------------
def phase_baselines(balls: pd.DataFrame, rain_affected_ids: set[int] | None = None) -> pd.DataFrame:
    """League runs per ball for each season x phase, for batters (per ball faced)
    and bowlers (per legal ball, runs charged to the bowler)."""
    b = balls
    if rain_affected_ids:
        b = b[~b["match_id"].isin(rain_affected_ids)]
    faced = b[b["ball_faced"]].groupby(["season", "phase"]).agg(
        bat_runs=("runs_batter", "sum"), balls_faced=("ball_faced", "size"))
    outs = b.groupby(["season", "phase"])["wicket"].sum().rename("dismissals")
    bowled = b.groupby(["season", "phase"]).agg(
        bowl_runs=("bowler_runs", "sum"), legal_balls=("legal_ball", "sum"),
        bowler_wkts=("bowler_wicket", "sum"))
    base = faced.join(outs).join(bowled)
    base["bat_rpb"] = base["bat_runs"] / base["balls_faced"]
    base["bowl_rpb"] = base["bowl_runs"] / base["legal_balls"]
    # League-average dismissal / wicket rates: an average player is expected to
    # lose (or take) this many wickets per ball, so only the excess is scored.
    base["out_rate"] = base["dismissals"] / base["balls_faced"]
    base["wkt_rate"] = base["bowler_wkts"] / base["legal_balls"]
    return base[["bat_rpb", "bowl_rpb", "out_rate", "wkt_rate"]].reset_index()


def run_expectancy(balls: pd.DataFrame) -> pd.DataFrame:
    """Average runs still to come in a first innings from each (ball, wickets lost) state.

    Uses first innings only (chases stop early when the target is reached).
    State = number of legal balls already bowled (0-119) and wickets lost."""
    fi = balls[(balls["innings"] == 1)].copy()
    fi = fi.sort_values(["match_id", "over", "ball"])
    fi["balls_done"] = fi.groupby("match_id")["legal_ball"].cumsum() - fi["legal_ball"].astype(int)
    fi["wkts_before"] = fi.groupby("match_id")["wicket"].cumsum() - fi["wicket"].astype(int)
    total = fi.groupby("match_id")["total_runs"].transform("sum")
    fi["runs_to_come"] = total - (fi.groupby("match_id")["total_runs"].cumsum() - fi["total_runs"])
    re_tab = (fi.groupby(["balls_done", "wkts_before"])["runs_to_come"]
              .agg(["mean", "size"]).reset_index())
    return re_tab


def wicket_values(balls: pd.DataFrame, min_cell: int = 30) -> pd.Series:
    """Runs a wicket costs the batting side, averaged by phase.

    For every wicket that fell at state (b balls done, w wickets down) the cost
    is RE(b, w) - RE(b, w + 1): how many fewer runs teams go on to score from
    the same point with one wicket fewer in hand. Cells with fewer than
    `min_cell` observations are ignored."""
    p = valuation_params()
    b = balls[balls["season"].isin(p["wicket_value_seasons"])]
    re_tab = run_expectancy(b)
    re_tab = re_tab[re_tab["size"] >= min_cell].set_index(["balls_done", "wkts_before"])["mean"]

    fi = b[(b["innings"] == 1)].copy().sort_values(["match_id", "over", "ball"])
    fi["balls_done"] = fi.groupby("match_id")["legal_ball"].cumsum() - fi["legal_ball"].astype(int)
    fi["wkts_before"] = fi.groupby("match_id")["wicket"].cumsum() - fi["wicket"].astype(int)
    w = fi[fi["wicket"]][["balls_done", "wkts_before", "phase"]]
    a = re_tab.reindex(list(zip(w["balls_done"], w["wkts_before"]))).to_numpy()
    c = re_tab.reindex(list(zip(w["balls_done"], w["wkts_before"] + 1))).to_numpy()
    w = w.assign(cost=a - c).dropna()
    return w.groupby("phase")["cost"].mean().reindex(PHASES)


# --------------------------------------------------------------------------
# Player-season impact
# --------------------------------------------------------------------------
def season_impact(bat: pd.DataFrame, bowl: pd.DataFrame, apps: pd.DataFrame,
                  baselines: pd.DataFrame, wkt_value: pd.Series) -> pd.DataFrame:
    """Impact per player x season (raw totals, per match, and shrunk)."""
    p = valuation_params()
    wv = wkt_value.rename("wkt_value").rename_axis("phase").reset_index()

    bt = bat.merge(baselines, on=["season", "phase"]).merge(wv, on="phase")
    # Wickets are scored relative to the league-average rate so that an
    # average batter and an average bowler both score 0.
    bt["bat_impact"] = (bt["runs"] - bt["balls_faced"] * bt["bat_rpb"]
                        - (bt["dismissals"] - bt["balls_faced"] * bt["out_rate"]) * bt["wkt_value"])
    bw = bowl.merge(baselines, on=["season", "phase"]).merge(wv, on="phase")
    bw["bowl_impact"] = (bw["legal_balls"] * bw["bowl_rpb"] - bw["runs_conceded"]
                         + (bw["wickets"] - bw["legal_balls"] * bw["wkt_rate"]) * bw["wkt_value"])

    # Phase-level table (kept for the phase breakdown).
    phase_tab = (bt[["player", "season", "phase", "bat_impact", "balls_faced"]]
                 .merge(bw[["player", "season", "phase", "bowl_impact", "legal_balls"]],
                        on=["player", "season", "phase"], how="outer").fillna(0))

    season = phase_tab.groupby(["player", "season"]).agg(
        bat_impact=("bat_impact", "sum"), bowl_impact=("bowl_impact", "sum"),
        balls_faced=("balls_faced", "sum"), balls_bowled=("legal_balls", "sum"),
    ).reset_index()
    m = apps.groupby(["player", "season"])["matches"].sum().reset_index()
    season = season.merge(m, on=["player", "season"], how="left")
    season["matches"] = season["matches"].fillna(1).clip(lower=1)

    season["bat_pm"] = season["bat_impact"] / season["matches"]
    season["bowl_pm"] = season["bowl_impact"] / season["matches"]
    season["bat_pm_adj"] = shrink(season["bat_pm"], season["balls_faced"], p["shrinkage_k_bat"])
    season["bowl_pm_adj"] = shrink(season["bowl_pm"], season["balls_bowled"], p["shrinkage_k_bowl"])
    season["impact_pm"] = season["bat_pm_adj"] + season["bowl_pm_adj"]

    # Per-phase impact per match (shrunk with the same factors) for breakdowns.
    phase_tab = phase_tab.merge(season[["player", "season", "matches", "balls_faced", "balls_bowled"]]
                                .rename(columns={"balls_faced": "bf_tot", "balls_bowled": "bb_tot"}),
                                on=["player", "season"])
    phase_tab["phase_pm"] = (
        shrink(phase_tab["bat_impact"] / phase_tab["matches"], phase_tab["bf_tot"], p["shrinkage_k_bat"])
        + shrink(phase_tab["bowl_impact"] / phase_tab["matches"], phase_tab["bb_tot"], p["shrinkage_k_bowl"])
    )
    return season, phase_tab


def shrink(raw: pd.Series | float, n: pd.Series | float, k: float):
    """Small-sample shrinkage toward zero (= league average): raw x n / (n + k)."""
    return raw * n / (n + k)


def weighted_impact(season: pd.DataFrame, phase_tab: pd.DataFrame, as_of: int,
                    weights: list[float] | None = None) -> pd.DataFrame:
    """Combine the 3 seasons before `as_of` into one Impact Score per player.

    as_of = the season being planned for (e.g. 2027 uses 2026, 2025, 2024)."""
    p = valuation_params()
    weights = weights or p["recency_weights"]
    window = [as_of - 1 - i for i in range(len(weights))]
    wmap = dict(zip(window, weights))
    s = season[season["season"].isin(window)].copy()
    s["w"] = s["season"].map(wmap)

    def agg(g: pd.DataFrame) -> pd.Series:
        w = g["w"] / g["w"].sum()  # re-normalise over seasons actually played
        return pd.Series({
            "impact": float((w * g["impact_pm"]).sum()),
            "bat_impact": float((w * g["bat_pm_adj"]).sum()),
            "bowl_impact": float((w * g["bowl_pm_adj"]).sum()),
            "consistency_sd": float(g["impact_pm"].std(ddof=0)) if len(g) > 1 else np.nan,
            "seasons_played": int(len(g)),
            "matches_3y": int(g["matches"].sum()),
            "balls_faced_3y": int(g["balls_faced"].sum()),
            "balls_bowled_3y": int(g["balls_bowled"].sum()),
            "last_season": int(g["season"].max()),
        })

    out = s.groupby("player").apply(agg, include_groups=False).reset_index()
    out = out[(out["balls_faced_3y"] + out["balls_bowled_3y"]) >= p["min_balls_total"]]

    # Phase breakdown, same weights.
    ph = phase_tab[phase_tab["season"].isin(window)].copy()
    ph["w"] = ph["season"].map(wmap)
    wsum = ph.groupby(["player", "season"])["w"].first().groupby("player").sum()
    ph["w"] = ph["w"] / ph["player"].map(wsum)
    phase_wide = (ph.assign(x=ph["w"] * ph["phase_pm"])
                  .pivot_table(index="player", columns="phase", values="x", aggfunc="sum")
                  .reindex(columns=PHASES).fillna(0).add_prefix("impact_"))
    out = out.merge(phase_wide.reset_index(), on="player", how="left")
    out["as_of"] = as_of
    return out.sort_values("impact", ascending=False).reset_index(drop=True)


def availability(apps: pd.DataFrame, team_m: pd.DataFrame, as_of: int, n: int = 3) -> pd.Series:
    """Share of their team's matches a player featured in over the last n seasons."""
    window = list(range(as_of - n, as_of))
    a = apps[apps["season"].isin(window)].merge(team_m, on=["season", "team"])
    g = a.groupby("player").agg(m=("matches", "sum"), tm=("team_matches", "sum"))
    return (g["m"] / g["tm"]).clip(upper=1).rename("availability")

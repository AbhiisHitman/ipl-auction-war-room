"""Feature tables built from the clean ball-level data.

* add_phase()           Powerplay (1-6) / Middle (7-15) / Death (16-20)
* batting_positions()   batting position of each batter in each innings
* batting_table()       player x season x phase batting totals
* bowling_table()       player x season x phase bowling totals
* appearances()         player x season x team matches played
* home_venues()         data-driven home ground per franchise
* venue_profiles()      how each ground plays (scoring rate, spin vs pace)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import valuation_params


def add_phase(balls: pd.DataFrame) -> pd.DataFrame:
    """Add a `phase` column and drop super overs."""
    phases = valuation_params()["phases"]
    out = balls[~balls["super_over"]].copy()
    out["phase"] = pd.cut(
        out["over"],
        bins=[0, phases["Powerplay"][1], phases["Middle"][1], phases["Death"][1]],
        labels=["Powerplay", "Middle", "Death"],
    ).astype(str)
    return out


def batting_positions(balls: pd.DataFrame) -> pd.DataFrame:
    """Batting position = order in which a batter first appears (as striker or
    non-striker) in an innings. Openers are positions 1-2."""
    seq = balls[["match_id", "innings", "batter", "non_striker"]].reset_index(drop=True)
    seq["order"] = np.arange(len(seq))
    long = pd.concat(
        [seq[["match_id", "innings", "order", "batter"]].rename(columns={"batter": "player"}),
         seq[["match_id", "innings", "order", "non_striker"]].rename(columns={"non_striker": "player"})]
    )
    first = long.groupby(["match_id", "innings", "player"])["order"].min().reset_index()
    first = first.sort_values(["match_id", "innings", "order"])
    # Striker before non-striker on the first ball: rank by (order, then name order from the ball).
    first["position"] = first.groupby(["match_id", "innings"]).cumcount() + 1
    return first[["match_id", "innings", "player", "position"]]


def batting_table(balls: pd.DataFrame) -> pd.DataFrame:
    """Runs, balls faced and dismissals per player x season x phase."""
    faced = balls[balls["ball_faced"]]
    bat = faced.groupby(["batter", "season", "phase"], observed=True).agg(
        balls_faced=("ball_faced", "size"),
        runs=("runs_batter", "sum"),
        fours=("runs_batter", lambda r: int((r == 4).sum())),
        sixes=("runs_batter", lambda r: int((r == 6).sum())),
        dots=("runs_batter", lambda r: int((r == 0).sum())),
    )
    # Dismissals are credited to whoever was out (striker or non-striker run out).
    outs = (balls[balls["wicket"]]
            .groupby(["player_dismissed", "season", "phase"], observed=True).size()
            .rename("dismissals"))
    outs.index = outs.index.set_names(["batter", "season", "phase"])
    bat = bat.join(outs, how="outer").fillna(0).reset_index().rename(columns={"batter": "player"})
    return bat


def bowling_table(balls: pd.DataFrame) -> pd.DataFrame:
    """Legal balls, runs conceded (excl. byes/leg-byes) and wickets per player x season x phase."""
    bowl = balls.groupby(["bowler", "season", "phase"], observed=True).agg(
        legal_balls=("legal_ball", "sum"),
        deliveries=("legal_ball", "size"),
        runs_conceded=("bowler_runs", "sum"),
        wickets=("bowler_wicket", "sum"),
        dots_bowled=("total_runs", lambda r: int((r == 0).sum())),
    ).reset_index().rename(columns={"bowler": "player"})
    return bowl


def appearances(match_players: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Matches played per player x season x team (from the named team sheets)."""
    mp = match_players.merge(matches[["match_id", "season"]], on="match_id")
    return (mp.groupby(["player", "season", "team"]).size()
            .rename("matches").reset_index())


def team_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Matches played by each franchise in each season."""
    long = pd.concat([matches[["season", "team1"]].rename(columns={"team1": "team"}),
                      matches[["season", "team2"]].rename(columns={"team2": "team"})])
    return long.groupby(["season", "team"]).size().rename("team_matches").reset_index()


def home_venues(matches: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """Home ground = the venue each franchise played most league matches at
    in the given seasons (teams play 7 home games, at most ~2 away per ground)."""
    m = matches[matches["season"].isin(seasons) & ~matches["is_playoff"]]
    long = pd.concat([m[["season", "venue", "team1"]].rename(columns={"team1": "team"}),
                      m[["season", "venue", "team2"]].rename(columns={"team2": "team"})])
    counts = long.groupby(["team", "venue"]).size().rename("matches").reset_index()
    counts = counts.sort_values(["team", "matches"], ascending=[True, False])
    top = counts.groupby("team").head(1).copy()
    top["share_of_team_matches"] = top["matches"] / long.groupby("team").size().reindex(top["team"]).values
    return top.reset_index(drop=True)


def venue_profiles(balls: pd.DataFrame, bowler_types: pd.Series, seasons: list[int]) -> pd.DataFrame:
    """How each ground plays relative to the league in `seasons`.

    bowler_types: Cricsheet name -> 'pace' / 'wrist_spin' / 'finger_spin'.
    Returns run rate index, and spin vs pace economy and strike-rate indices
    (1.0 = league average; spin_econ_index < 1 means spin is cheaper here)."""
    b = balls[balls["season"].isin(seasons)].copy()
    b["btype"] = b["bowler"].map(bowler_types)
    b["is_spin"] = b["btype"].isin(["wrist_spin", "finger_spin"])
    b["is_pace"] = b["btype"].eq("pace")

    def summarise(g: pd.DataFrame) -> pd.Series:
        legal = g["legal_ball"].sum()
        sp, pc = g[g["is_spin"]], g[g["is_pace"]]
        return pd.Series({
            "balls": legal,
            "run_rate": 6 * g["total_runs"].sum() / max(legal, 1),
            "death_run_rate": 6 * g.loc[g["phase"] == "Death", "total_runs"].sum()
                              / max(g.loc[g["phase"] == "Death", "legal_ball"].sum(), 1),
            "spin_econ": 6 * sp["bowler_runs"].sum() / max(sp["legal_ball"].sum(), 1),
            "pace_econ": 6 * pc["bowler_runs"].sum() / max(pc["legal_ball"].sum(), 1),
            "spin_balls_per_wkt": sp["legal_ball"].sum() / max(sp["bowler_wicket"].sum(), 1),
            "pace_balls_per_wkt": pc["legal_ball"].sum() / max(pc["bowler_wicket"].sum(), 1),
            "spin_share_of_overs": sp["legal_ball"].sum() / max(legal, 1),
        })

    league = summarise(b)
    per = b.groupby("venue").apply(summarise, include_groups=False)
    for col in ["run_rate", "death_run_rate", "spin_econ", "pace_econ",
                "spin_balls_per_wkt", "pace_balls_per_wkt", "spin_share_of_overs"]:
        per[f"{col}_index"] = per[col] / league[col]
    # Relative spin advantage: >1 means spin does better (vs pace) here than in the league.
    per["spin_advantage"] = (per["pace_econ_index"] / per["spin_econ_index"]).round(3)
    return per.reset_index()

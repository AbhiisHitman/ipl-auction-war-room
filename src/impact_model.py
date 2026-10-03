"""Squad strength -> wins -> playoff chance (the 'what is it worth' chain).

1. Planned strength in season S = sum of the pre-season Impact Scores (as of S)
   of the 12 players who played most for that team in S.
2. Realised team impact = what those players actually produced in S (runs per
   match above average, unshrunk).
3. Structural link:   win% = a + b x realised impact        (R^2 ~ 0.5)
   Realisation link:  realised = c + rho x planned strength (rho < 1: T20 noise,
                      form and injuries mean only part of a planned gain shows up)
   => expected win% = a + b x (c + rho x planned strength)
4. Playoff chance from expected win% with a binomial model over 14 league
   games, using the empirical number of wins the 4th-placed team needed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from math import comb

from .optimiser import STARTERS


@dataclass
class WinModel:
    a: float  # structural intercept
    b: float  # win % per run/match of realised team impact
    c: float  # realisation intercept
    rho: float  # realised runs per run of planned strength
    r2_structural: float
    r2_realisation: float
    n: int
    playoff_wins_threshold: int
    data: pd.DataFrame

    @property
    def slope(self) -> float:
        """Expected win % per +1 run/match of planned squad strength."""
        return self.b * self.rho

    def win_pct(self, strength: float) -> float:
        return float(np.clip(self.a + self.b * (self.c + self.rho * strength), 0.05, 0.95))

    def playoff_prob(self, win_pct: float, games: int = 14) -> float:
        """P(wins >= threshold) + half of P(wins == threshold - 1) (tie-breaks on NRR)."""
        t = self.playoff_wins_threshold
        pmf = [comb(games, k) * win_pct**k * (1 - win_pct) ** (games - k) for k in range(games + 1)]
        p_ge = sum(pmf[t:])
        p_edge = pmf[t - 1]
        return float(p_ge + 0.5 * p_edge)


def team_season_strength(apps: pd.DataFrame, impact_by_season: dict[int, pd.DataFrame],
                         repl_by_season: dict[int, float]) -> pd.DataFrame:
    rows = []
    for s, imp in impact_by_season.items():
        a = apps[apps["season"] == s]
        imap = imp.set_index("player")["impact"]
        for team, g in a.groupby("team"):
            top = g.sort_values("matches", ascending=False).head(STARTERS)
            vals = top["player"].map(imap).fillna(repl_by_season[s])
            rows.append({"season": s, "team": team, "strength": float(vals.sum()),
                         "players_with_data": int(top["player"].isin(imap.index).sum())})
    return pd.DataFrame(rows)


def team_win_pct(matches: pd.DataFrame) -> pd.DataFrame:
    m = matches[~matches["is_playoff"]]
    long = pd.concat([m[["season", "team1", "winner"]].rename(columns={"team1": "team"}),
                      m[["season", "team2", "winner"]].rename(columns={"team2": "team"})])
    long["win"] = (long["winner"] == long["team"]).astype(float)
    long = long[long["winner"].notna()]  # drop no-results
    return long.groupby(["season", "team"])["win"].agg(["mean", "size"]).rename(
        columns={"mean": "win_pct", "size": "games"}).reset_index()


def fourth_place_wins(matches: pd.DataFrame, seasons: list[int]) -> int:
    from .team_strategy import league_table
    w = [int(league_table(matches, s).iloc[3]["wins"]) for s in seasons]
    return int(round(float(np.median(w))))


def realised_team_impact(apps: pd.DataFrame, season_impact: pd.DataFrame,
                         team_m: pd.DataFrame) -> pd.DataFrame:
    """Runs per match above average that each team actually produced in a season."""
    x = apps.merge(season_impact[["player", "season", "bat_impact", "bowl_impact"]],
                   on=["player", "season"], how="left")
    share = x["matches"] / x.groupby(["player", "season"])["matches"].transform("sum")
    x["tot"] = (x["bat_impact"].fillna(0) + x["bowl_impact"].fillna(0)) * share
    c = x.groupby(["season", "team"])["tot"].sum().reset_index().merge(team_m, on=["season", "team"])
    c["realised"] = c["tot"] / c["team_matches"]
    return c[["season", "team", "realised"]]


def fit_win_model(strength: pd.DataFrame, wins: pd.DataFrame, matches: pd.DataFrame,
                  realised: pd.DataFrame) -> WinModel:
    import statsmodels.api as sm  # only needed when fitting (pipeline), not in the web API
    d = strength.merge(wins, on=["season", "team"]).merge(realised, on=["season", "team"])
    s1 = sm.OLS(d["win_pct"], sm.add_constant(d["realised"])).fit()
    s2 = sm.OLS(d["realised"], sm.add_constant(d["strength"])).fit()
    recent = sorted(d["season"].unique())[-5:]
    return WinModel(a=float(s1.params["const"]), b=float(s1.params["realised"]),
                    c=float(s2.params["const"]), rho=float(s2.params["strength"]),
                    r2_structural=float(s1.rsquared), r2_realisation=float(s2.rsquared),
                    n=len(d), playoff_wins_threshold=fourth_place_wins(matches, recent), data=d)

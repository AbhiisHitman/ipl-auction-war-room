"""Team-specific priorities: what should THIS franchise prioritise?

Three data-driven inputs make every team's plan different:
  1. Squad gaps    - role coverage matrix (Red / Amber / Green)
  2. Home ground   - does spin or pace work better there? is the death costly?
  3. Situation     - 2026 finish, squad age, purse and overseas slots left
They combine into a role weight used by the optimiser and a short brief.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import assumptions
from .squad import ROLES

SPIN_ROLES = {"Wrist spinner", "Finger spinner"}
PACE_ROLES = {"Powerplay pacer", "Death pacer"}
DEATH_ROLES = {"Death pacer", "Finisher"}


def venue_multipliers(profile: pd.Series | None) -> dict[str, float]:
    """Role multipliers from how the home ground plays (1.0 = neutral)."""
    a = assumptions()["strategy"]
    e = a["venue_elasticity"]["value"]
    lo, hi = a["venue_weight_bounds"]["value"]
    mult = {r: 1.0 for r in ROLES}
    if profile is None or profile.empty:
        return mult
    s = float(profile.get("spin_advantage", 1.0) or 1.0)
    d = float(profile.get("death_run_rate_index", 1.0) or 1.0)
    for r in SPIN_ROLES:
        mult[r] *= s ** e
    for r in PACE_ROLES:
        mult[r] *= (1 / s) ** e
    for r in DEATH_ROLES:
        mult[r] *= d ** e
    return {r: float(np.clip(v, lo, hi)) for r, v in mult.items()}


def role_weights(coverage: pd.DataFrame, venue_mult: dict[str, float]) -> dict[str, float]:
    need = assumptions()["strategy"]["role_need_weight"]["value"]
    status = coverage.set_index("role")["status"]
    return {r: round(need[status.get(r, "Green")] * venue_mult.get(r, 1.0), 3) for r in ROLES}


def league_table(matches: pd.DataFrame, season: int) -> pd.DataFrame:
    """Points table from league matches (2 per win, 1 per no-result/tie
    without super over). Net run rate is not computed (limitation)."""
    m = matches[(matches["season"] == season) & ~matches["is_playoff"]]
    teams = pd.unique(m[["team1", "team2"]].values.ravel())
    rows = []
    for t in teams:
        tm = m[(m["team1"] == t) | (m["team2"] == t)]
        wins = (tm["winner"] == t).sum()
        nr = tm["winner"].isna().sum()
        rows.append({"team": t, "played": len(tm), "wins": int(wins), "no_result": int(nr),
                     "points": int(2 * wins + nr)})
    tab = pd.DataFrame(rows).sort_values(["points", "wins"], ascending=False).reset_index(drop=True)
    tab["position"] = np.arange(1, len(tab) + 1)
    po = matches[(matches["season"] == season) & matches["is_playoff"]]
    playoff_teams = set(po["team1"]).union(po["team2"])
    tab["made_playoffs"] = tab["team"].isin(playoff_teams)
    final = po.sort_values("date").tail(1)
    tab["champion"] = tab["team"].eq(final["winner"].iloc[0]) if len(final) else False
    return tab


def recommended_stance(finish: pd.Series, core_age: float) -> tuple[str, str]:
    """Win Now vs Long-Term Build, with the reason."""
    if bool(finish.get("made_playoffs", False)):
        return "Win Now", f"Made the 2026 playoffs (finished #{int(finish['position'])}); protect the window."
    if core_age >= 30:
        return "Long-Term Build", f"Missed the 2026 playoffs with an ageing core (avg age of top-12: {core_age:.1f})."
    if int(finish.get("position", 10)) >= 8:
        return "Long-Term Build", f"Finished #{int(finish['position'])} in 2026; rebuild around younger players."
    return "Win Now", f"Missed the playoffs narrowly (#{int(finish['position'])}) with a young core (avg age {core_age:.1f})."


def team_brief(team: str, coverage: pd.DataFrame, weights: dict[str, float],
               venue: str, profile: pd.Series | None, finish: pd.Series,
               squad: pd.DataFrame, purse_left_lakh: float, overseas_left: int) -> dict:
    """Plain-English priorities for one franchise."""
    top12 = squad.sort_values("impact", ascending=False).head(12)
    core_age = float(top12["age_at_auction"].mean()) if top12["age_at_auction"].notna().any() else np.nan
    stance, why = recommended_stance(finish, core_age if not np.isnan(core_age) else 28)
    reds = coverage[coverage["status"] == "Red"]
    ambers = coverage[coverage["status"] == "Amber"]
    pri = []
    for _, r in reds.iterrows():
        pri.append(f"Fix {r['role']} (Red): {r['explanation']}.")
    for _, r in ambers.iterrows():
        pri.append(f"Upgrade {r['role']} (Amber): {r['explanation']}.")
    if profile is not None and not profile.empty:
        s = float(profile.get("spin_advantage", 1))
        if s >= 1.05:
            pri.append(f"Home ground ({venue}) favours spin: pace economy is {s:.2f}x spin economy "
                       f"relative to the league, so spinners get a higher weight.")
        elif s <= 0.95:
            pri.append(f"Home ground ({venue}) favours pace: spin goes {1 / s:.2f}x as expensive "
                       f"relative to the league, so pacers get a higher weight.")
        d = float(profile.get("death_run_rate_index", 1))
        if d >= 1.05:
            pri.append(f"Death overs at {venue} cost {d - 1:.0%} more than the league average: "
                       f"value death bowling and finishing.")
    return {
        "team": team,
        "stance": stance,
        "stance_reason": why,
        "home_venue": venue,
        "finish_2026": int(finish.get("position", 0)),
        "made_playoffs_2026": bool(finish.get("made_playoffs", False)),
        "core_age": None if np.isnan(core_age) else round(core_age, 1),
        "purse_left_cr": round(purse_left_lakh / 100, 2),
        "overseas_slots_left": int(overseas_left),
        "priorities": pri,
        "role_weights": weights,
        "red_roles": reds["role"].tolist(),
        "amber_roles": ambers["role"].tolist(),
    }

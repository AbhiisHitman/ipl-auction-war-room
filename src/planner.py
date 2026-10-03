"""Run one franchise's auction plan (optimiser + impact chain).

Kept free of heavy analysis imports (statsmodels, scipy) so the web API can
load it inside a small serverless function. Used by the pipeline and the API.
"""
from __future__ import annotations

import pandas as pd

from .config import assumptions
from .economics import default_inputs, expected_profit
from .optimiser import STARTERS, optimise, squad_strength

PLAN_SEASON = 2027  # impact "as of" the next season to be played
STANCE_TO_STRATEGY = {"Win Now": "win_now", "Long-Term Build": "long_term"}


def pools(players: pd.DataFrame, team: str, mode: str) -> pd.Series:
    """Who can this team buy?

    mini: unsigned players + players other teams are projected to release
          (salary >= 1.5x fair value and outside their top 12).
    mega: everyone except the top-N players each rival is projected to retain."""
    alive = ~players["retired"] & players["overseas"].notna()
    recent = players["contract_season"].fillna(0).ge(2025) | players["last_season"].fillna(0).ge(2025)
    base = alive & recent
    if mode == "mini_2027":
        return base & (players["current_team"].isna() | players["projected_release"])
    n_keep = assumptions()["strategy"]["mega_other_team_retentions"]["value"]
    rank = players.groupby("current_team")["impact"].rank(ascending=False, method="first")
    rival_kept = players["current_team"].notna() & players["current_team"].ne(team) & rank.le(n_keep)
    return base & ~rival_kept & players["current_team"].ne(team)


def flag_projected_releases(players: pd.DataFrame) -> pd.DataFrame:
    p = players.copy()
    rank = p.groupby("current_team")["impact"].rank(ascending=False, method="first")
    overpaid = p["current_salary_lakh"] >= 1.5 * p["fair_value_mini_2027"].fillna(30)
    p["projected_release"] = p["current_team"].notna() & overpaid & ~rank.le(STARTERS)
    return p


def run_team(ctx: dict, team: str, mode: str, strategy: str, inflation: float | None = None,
             locked=None, excluded=None) -> dict:
    """One optimiser run + the impact chain. Used by the pipeline and the app."""
    players, wm = ctx["players"], ctx["win_model"]
    mask = pools(players, team, mode)
    res = optimise(players, team, mode, ctx["role_weights"][team], strategy, inflation,
                   locked, excluded, pool_filter=mask)
    repl = ctx["repl"][PLAN_SEASON]
    cur = players[players["current_team"].eq(team)]
    s_before = squad_strength(cur["impact"], repl)
    s_after = squad_strength(res.squad["impact"], repl)
    w0, w1 = wm.win_pct(s_before), wm.win_pct(s_after)
    p0, p1 = wm.playoff_prob(w0), wm.playoff_prob(w1)
    title = assumptions()["strategy"]["title_prob_given_playoffs"]["value"]
    venue = ctx["homes"].set_index("team").loc[team, "venue"]
    e0 = expected_profit(default_inputs(team, venue, cur["current_salary_lakh"].sum() / 100), p0, title)
    e1 = expected_profit(default_inputs(team, venue, res.purse_used_lakh / 100), p1, title)
    return {"result": res, "pool_mask": mask, "summary": {
        "team": team, "mode": mode, "strategy": strategy, "rival_inflation": res.params["rival_inflation"],
        "status": res.status, "solve_seconds": res.solve_seconds,
        "purse_used_cr": res.purse_used_lakh / 100, "purse_total_cr": res.purse_total_lakh / 100,
        "squad_size": len(res.squad), "buys": int((res.squad["action"] == "Buy").sum()),
        "releases": int(len(res.released)), "roles_covered": int(res.role_counts["covered"].sum()),
        "strength_before": round(s_before, 2), "strength_after": round(s_after, 2),
        "win_pct_before": round(w0, 3), "win_pct_after": round(w1, 3),
        "playoff_prob_before": round(p0, 3), "playoff_prob_after": round(p1, 3),
        "exp_revenue_before_cr": round(e0["expected_revenue_cr"], 1),
        "exp_revenue_after_cr": round(e1["expected_revenue_cr"], 1),
        "exp_profit_before_cr": round(e0["expected_profit_cr"], 1),
        "exp_profit_after_cr": round(e1["expected_profit_cr"], 1),
    }}

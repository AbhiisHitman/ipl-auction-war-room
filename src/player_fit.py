"""Player -> team fit: where would a player add the most?

For player p and franchise t (2027 squads):
  gain   = V(top-12 of squad_t + p) - V(top-12 of squad_t)
           where V sums (impact - replacement) x t's role weight
           -> how much stronger t's best 12 get, valued by t's own gaps
  starter: would p be in t's best 12?
  gap    : the most urgent coverage status among p's roles at t (Red > Amber > Green)
  afford : does t have purse room (before releases) and an overseas slot? info only
  win %  : extra expected win % from the unweighted strength gain (win model slope)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .optimiser import STARTERS


def _value(impact: pd.Series, roles: pd.Series, weights: dict[str, float], repl: float) -> pd.Series:
    w = roles.apply(lambda rl: max([weights.get(r, 1.0) for r in rl], default=1.0))
    return (impact.fillna(repl) - repl) * w


def _top_sum(v: pd.Series) -> float:
    return float(v.sort_values(ascending=False).head(STARTERS).clip(lower=0).sum())


def player_team_fit(players: pd.DataFrame, coverage: pd.DataFrame, briefs: dict,
                    repl: float, win_slope: float) -> pd.DataFrame:
    teams = list(briefs.keys())
    cand = players[players["has_impact"] & ~players["retired"]].copy()
    rows = []
    for t in teams:
        w = briefs[t]["role_weights"]
        status = coverage[coverage["team"] == t].set_index("role")["status"]
        squad = players[players["current_team"].eq(t)]
        base_v = _value(squad["impact"], squad["roles"], w, repl)
        base = _top_sum(base_v)
        base_raw = float(squad["impact"].fillna(repl).sort_values(ascending=False).head(STARTERS).sum())
        twelfth = base_v.sort_values(ascending=False).head(STARTERS).min() if len(base_v) else -np.inf
        purse_left = briefs[t]["purse_left_cr"] * 100
        ov_left = briefs[t]["overseas_slots_left"]
        cand_v = _value(cand["impact"], cand["roles"], w, repl)
        for idx, p in cand.iterrows():
            own = bool(p["current_team"] == t) if pd.notna(p["current_team"]) else False
            if own:
                v_without = base_v.drop(idx, errors="ignore")
                gain = base - _top_sum(v_without)
                raw_without = squad.drop(idx, errors="ignore")["impact"].fillna(repl)
                raw_gain = base_raw - float(raw_without.sort_values(ascending=False).head(STARTERS).sum())
                starter = cand_v[idx] >= v_without.sort_values(ascending=False).head(STARTERS).min()
            else:
                gain = _top_sum(pd.concat([base_v, pd.Series([cand_v[idx]])])) - base
                raw_gain = float(pd.concat([squad["impact"].fillna(repl), pd.Series([p["impact"]])])
                                 .sort_values(ascending=False).head(STARTERS).sum()) - base_raw
                starter = cand_v[idx] > twelfth
            sts = [status.get(r, "Green") for r in p["roles"]]
            gap = "Red" if "Red" in sts else ("Amber" if "Amber" in sts else ("Green" if sts else None))
            gap_role = next((r for r, s in zip(p["roles"], sts) if s == gap), None) if gap in ("Red", "Amber") else None
            price = p.get("expected_price_mini_2027")
            afford = own or (pd.notna(price) and price <= purse_left)
            ov_ok = own or not (pd.notna(p["overseas"]) and bool(p["overseas"])) or ov_left > 0
            rows.append({
                "player": p["player"], "team": t, "own_team": bool(own),
                "fit_gain": round(gain, 3), "strength_gain": round(raw_gain, 3),
                "win_pct_gain": round(raw_gain * win_slope, 4),
                "starter": bool(starter), "gap": gap, "gap_role": gap_role,
                "purse_room_now": bool(afford), "overseas_slot": bool(ov_ok),
            })
    fit = pd.DataFrame(rows)
    # Rank teams for each player by gap-weighted gain. Purse room is shown as
    # information only: in a mini-auction teams free money by releasing players.
    fit["fit_rank"] = fit.groupby("player")["fit_gain"].rank(ascending=False, method="first").astype(int)
    return fit

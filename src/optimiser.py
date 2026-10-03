"""Squad optimiser (PuLP / CBC).

Decision: which players to keep / retain, and whom to buy.

Objective  maximise  sum(value_i * starter_i) + 0.1 * sum(value_i * in_squad_i)
                     - lambda * total cost
           value_i = (impact_i - replacement level) * role weight_i
           lambda  = opportunity cost of a crore (share of the pool's typical value per crore)
           -> the 12 who will play (XI + Impact Player) carry the value; depth
              counts 10%.
Constraints (from config/rules.yaml):
  * total cost <= purse, and >= minimum-spend share of the purse
  * squad size between min and max; overseas <= cap; overseas starters <= 4
  * starters <= 12, and a starter must be in the squad
  * minimum number of players per role (soft: shortfall is allowed at a big penalty)
  * locked players must be in; excluded players must be out
Mini-auction: current players can be kept at their salary or released.
Mega-auction: up to 6 retentions at the slab costs; everyone else must be
              (re-)bought at expected auction cost.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pulp

from .config import assumptions, rules
from .squad import ROLES

STARTERS = 12  # XI + Impact Player
BENCH_WEIGHT = 0.1
ROLE_SHORTFALL_PENALTY = 50.0


@dataclass
class OptimiserResult:
    status: str
    squad: pd.DataFrame
    released: pd.DataFrame
    purse_used_lakh: float
    purse_total_lakh: float
    strength_before: float
    strength_after: float
    role_counts: pd.DataFrame
    solve_seconds: float
    params: dict = field(default_factory=dict)


def age_factor(age: pd.Series) -> pd.Series:
    c = assumptions()["strategy"]["age_curve"]["value"]
    f = (1 - c["decline_per_year"] * (age - c["peak_until"]).clip(lower=0)
         + c["youth_bonus_per_year"] * (c["youth_from"] - age).clip(lower=0))
    return f.clip(c["floor"], c["cap"]).fillna(1.0)


def strategy_impact(players: pd.DataFrame, strategy: str) -> pd.Series:
    """Win Now uses the win-now recency weights (column impact_win_now);
    Long-Term multiplies positive impact by the age factor (and divides negative)."""
    if strategy == "win_now":
        return players["impact_win_now"].fillna(players["impact"])
    imp = players["impact"]
    f = age_factor(players["age_at_auction"])
    return np.where(imp >= 0, imp * f, imp / f)


def squad_strength(impacts: pd.Series, repl: float) -> float:
    """Sum of the best 12 impacts (missing data = replacement level)."""
    return float(impacts.fillna(repl).sort_values(ascending=False).head(STARTERS).sum())


def optimise(players: pd.DataFrame, team: str, mode: str, role_weight: dict[str, float],
             strategy: str = "win_now", rival_inflation: float | None = None,
             locked: list[str] | None = None, excluded: list[str] | None = None,
             pool_filter: pd.Series | None = None, time_limit: int = 20) -> OptimiserResult:
    """Run the optimiser for one team.

    players: master table with fair_value_<mode>, roles, current_team, etc.
    pool_filter: boolean Series marking who is available to buy (default: not
                 contracted to another team for the current season)."""
    t0 = time.time()
    R = rules()
    A = assumptions()["strategy"]
    cfg = R["modes"][mode]
    common = R["common"]
    purse = float(cfg["purse_lakh"]["value"])
    infl = A["rival_inflation"]["value"] if rival_inflation is None else rival_inflation
    locked, excluded = set(locked or []), set(excluded or [])

    df = players.copy()
    df["eval_impact"] = strategy_impact(df, strategy)
    repl = float(df.loc[df["has_impact"], "eval_impact"].quantile(A["replacement_level_percentile"]["value"]))
    df["eval_impact"] = df["eval_impact"].fillna(repl)
    df["role_w"] = df["roles"].apply(lambda rl: max([role_weight.get(r, 1.0) for r in rl], default=1.0))
    df["value"] = (df["eval_impact"] - repl) * df["role_w"]

    own = df["current_team"].eq(team)
    pool = pool_filter if pool_filter is not None else df["current_team"].isna()
    df = df[own | pool].copy()
    own = df["current_team"].eq(team)

    # Cost to win a player at auction = likely clearing price x (1 + rival inflation).
    price_col = f"expected_price_{mode}"
    floor = common["min_base_price_lakh"]["value"]
    ov_cap = common["overseas_max_fee_lakh"]["value"]
    exp_cost = (df[price_col].fillna(floor) * (1 + infl)).clip(lower=floor)
    exp_cost = np.where(df["overseas"].fillna(False).astype(bool), np.minimum(exp_cost, ov_cap), exp_cost)
    df["expected_cost_lakh"] = np.round(exp_cost, 0)
    df["is_overseas"] = df["overseas"].fillna(False).astype(bool)
    df["is_capped"] = df["capped"].fillna(True).astype(bool)

    prob = pulp.LpProblem(f"squad_{team}_{mode}", pulp.LpMaximize)
    idx = list(df.index)
    buy = {i: pulp.LpVariable(f"buy_{i}", cat="Binary") for i in idx}
    keep = {i: pulp.LpVariable(f"keep_{i}", cat="Binary") for i in idx if own[i]}
    start = {i: pulp.LpVariable(f"start_{i}", cat="Binary") for i in idx}
    in_squad = {i: buy[i] + (keep[i] if i in keep else 0) for i in idx}

    # Cost of keeping own players
    if mode == "mini_2027":
        keep_cost = pulp.lpSum(df.at[i, "current_salary_lakh"] * keep[i] for i in keep)
        retention_constraints = []
        # A released player can't be bought back in the same window (same auction pool is
        # other teams' releases); own players are keep-or-release only.
        for i in keep:
            prob += buy[i] == 0
    else:  # mega: slab retentions
        n_cap = pulp.lpSum(keep[i] for i in keep if df.at[i, "is_capped"])
        n_unc = pulp.lpSum(keep[i] for i in keep if not df.at[i, "is_capped"])
        slabs = cfg["capped_retention_cost_cumulative_lakh"]["value"]
        y = {n: pulp.LpVariable(f"ncap_{n}", cat="Binary") for n in range(len(slabs) + 1)}
        prob += pulp.lpSum(y.values()) == 1
        prob += n_cap == pulp.lpSum(n * y[n] for n in y)
        keep_cost = (pulp.lpSum(([0] + slabs)[n] * y[n] for n in y)
                     + cfg["uncapped_retention_cost_lakh"]["value"] * n_unc)
        prob += n_cap + n_unc <= cfg["max_retentions"]["value"]
        prob += n_cap <= cfg["max_capped_retentions"]["value"]
        prob += n_unc <= cfg["max_uncapped_retentions"]["value"]
        for i in keep:  # retain OR re-buy, not both
            prob += keep[i] + buy[i] <= 1

    buy_cost = pulp.lpSum(df.at[i, "expected_cost_lakh"] * buy[i] for i in idx)
    total_cost = keep_cost + buy_cost
    prob += total_cost <= purse
    prob += total_cost >= common["min_spend_pct"]["value"] * purse

    size = pulp.lpSum(in_squad.values())
    prob += size >= common["squad_min"]["value"]
    prob += size <= common["squad_max"]["value"]
    prob += pulp.lpSum(in_squad[i] for i in idx if df.at[i, "is_overseas"]) <= common["overseas_max"]["value"]

    prob += pulp.lpSum(start.values()) <= STARTERS
    for i in idx:
        prob += start[i] <= in_squad[i]
    prob += pulp.lpSum(start[i] for i in idx if df.at[i, "is_overseas"]) <= common["overseas_in_xi_max"]["value"]

    # Role minimums (soft)
    need = A["role_min_counts"]["value"]
    short = {r: pulp.LpVariable(f"short_{r.replace(' ', '_').replace('-', '_')}", lowBound=0) for r in ROLES}
    for r in ROLES:
        holders = [i for i in idx if r in df.at[i, "roles"]]
        prob += pulp.lpSum(in_squad[i] for i in holders) + short[r] >= need.get(r, 0)

    # Locks / exclusions (by Cricsheet name or display name)
    for i in idx:
        names = {df.at[i, "player"], df.at[i, "display_name"]}
        if names & locked:
            prob += in_squad[i] == 1
        if names & excluded:
            prob += in_squad[i] == 0

    # Opportunity cost of the purse: a crore must buy at least `share` of the
    # value a typical auction crore buys, otherwise it is better left unspent
    # (salary is a P&L cost). Data-driven: median value-per-crore in the pool.
    # Market rate = total value / total cost of positive-value pool players
    # (a ratio of sums, so Rs 30-lakh fillers don't dominate).
    pos = df[(df["value"] > 0) & ~own]
    typical = float(pos["value"].sum() / (pos["expected_cost_lakh"].sum() / 100)) if len(pos) else 0.0
    lam = A["purse_opportunity_cost_share"]["value"] * typical / 100  # per lakh
    prob += (pulp.lpSum(df.at[i, "value"] * start[i] for i in idx)
             + BENCH_WEIGHT * pulp.lpSum(df.at[i, "value"] * in_squad[i] for i in idx)
             - lam * total_cost
             - ROLE_SHORTFALL_PENALTY * pulp.lpSum(short.values()))

    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit))
    status = pulp.LpStatus[prob.status]

    def val(v) -> float:
        return float(v.value() or 0) if hasattr(v, "value") else float(v)

    df["selected"] = [round(val(in_squad[i])) == 1 for i in idx]
    df["starter"] = [round(start[i].value() or 0) == 1 for i in idx]
    df["action"] = None
    if mode == "mini_2027":
        df.loc[own & df["selected"], "action"] = "Retain"
    else:
        kept = {i for i in keep if round(keep[i].value() or 0) == 1}
        df.loc[[i for i in idx if i in kept], "action"] = "Retain"
        df.loc[own & df["selected"] & df["action"].isna(), "action"] = "Buy back"
    df.loc[~own & df["selected"], "action"] = "Buy"
    df.loc[own & ~df["selected"], "action"] = "Release"
    df["cost_lakh"] = np.where(df["action"] == "Retain",
                               df["current_salary_lakh"] if mode == "mini_2027" else np.nan,
                               np.where(df["action"].isin(["Buy", "Buy back"]), df["expected_cost_lakh"], 0))

    squad = df[df["selected"]].sort_values(["starter", "value"], ascending=False)
    released = df[df["action"] == "Release"]
    used = float(pulp.value(total_cost) or 0)
    if mode == "mega_2028":
        # Spread the slab cost over retained players for display.
        ret = squad["action"] == "Retain"
        ret_cost = float(pulp.value(keep_cost) or 0)
        squad.loc[ret, "cost_lakh"] = ret_cost / max(int(ret.sum()), 1)

    counts = pd.DataFrame({
        "role": ROLES,
        "needed": [need.get(r, 0) for r in ROLES],
        "in_squad": [int(sum(r in rl for rl in squad["roles"])) for r in ROLES],
    })
    counts["covered"] = counts["in_squad"] >= counts["needed"]

    before = squad_strength(df.loc[own, "eval_impact"], repl)
    after = squad_strength(squad["eval_impact"], repl)
    return OptimiserResult(
        status=status, squad=squad, released=released, purse_used_lakh=round(used, 0),
        purse_total_lakh=purse, strength_before=round(before, 2), strength_after=round(after, 2),
        role_counts=counts, solve_seconds=round(time.time() - t0, 2),
        params={"team": team, "mode": mode, "strategy": strategy, "rival_inflation": infl,
                "replacement_level": round(repl, 3), "lambda_per_cr": round(lam * 100, 4), "locked": sorted(locked), "excluded": sorted(excluded)},
    )


def check_constraints(res: OptimiserResult) -> dict[str, bool]:
    """Independent re-check of every hard constraint on a solution (used by tests)."""
    R = rules()
    c = R["common"]
    sq = res.squad
    n = len(sq)
    ov = int(sq["is_overseas"].sum())
    ov_start = int(sq.loc[sq["starter"], "is_overseas"].sum())
    return {
        "purse": res.purse_used_lakh <= res.purse_total_lakh + 1e-6,
        "min_spend": res.purse_used_lakh >= c["min_spend_pct"]["value"] * res.purse_total_lakh - 1,
        "squad_min": n >= c["squad_min"]["value"],
        "squad_max": n <= c["squad_max"]["value"],
        "overseas": ov <= c["overseas_max"]["value"],
        "overseas_starters": ov_start <= c["overseas_in_xi_max"]["value"],
        "starters": int(sq["starter"].sum()) <= STARTERS,
        "locked_in": all(any(x in (p, d) for p, d in zip(sq["player"], sq["display_name"]))
                         for x in res.params["locked"]),
        "excluded_out": not any(x in (p, d) for p, d in zip(sq["player"], sq["display_name"])
                                for x in res.params["excluded"]),
    }


# --------------------------------------------------------------------------
# Reduced model, identical to the Excel Solver workbook
# --------------------------------------------------------------------------
def solver_candidates(players: pd.DataFrame, team: str, role_weight: dict[str, float],
                      pool_filter: pd.Series, n_pool: int = 60, strategy: str = "win_now",
                      rival_inflation: float | None = None) -> tuple[pd.DataFrame, float]:
    """Own squad + the top-n pool candidates by value, with value and cost columns
    (mini-auction). Returns (candidates, lambda per lakh)."""
    A = assumptions()["strategy"]
    floor = rules()["common"]["min_base_price_lakh"]["value"]
    ov_cap = rules()["common"]["overseas_max_fee_lakh"]["value"]
    infl = A["rival_inflation"]["value"] if rival_inflation is None else rival_inflation
    df = players.copy()
    df["eval_impact"] = strategy_impact(df, strategy)
    repl = float(df.loc[df["has_impact"], "eval_impact"].quantile(A["replacement_level_percentile"]["value"]))
    df["eval_impact"] = df["eval_impact"].fillna(repl)
    df["role_w"] = df["roles"].apply(lambda rl: max([role_weight.get(r, 1.0) for r in rl], default=1.0))
    df["value"] = ((df["eval_impact"] - repl) * df["role_w"]).round(3)
    own = df["current_team"].eq(team)
    exp = (df["expected_price_mini_2027"].fillna(floor) * (1 + infl)).clip(lower=floor)
    exp = np.where(df["overseas"].fillna(False).astype(bool), np.minimum(exp, ov_cap), exp)
    df["cost_lakh"] = np.where(own, df["current_salary_lakh"], np.round(exp, 0))
    pool = df[pool_filter & ~own & (df["value"] > 0)].sort_values("value", ascending=False).head(n_pool)
    cand = pd.concat([df[own], pool])
    cand["owner"] = np.where(cand["current_team"].eq(team), "own", "pool")
    cand["is_overseas"] = cand["overseas"].fillna(False).astype(bool)
    pos = cand[(cand["value"] > 0) & cand["owner"].eq("pool")]
    typical = float(pos["value"].sum() / (pos["cost_lakh"].sum() / 100)) if len(pos) else 0.0
    lam = A["purse_opportunity_cost_share"]["value"] * typical / 100
    return cand.reset_index(drop=True), lam


def optimise_simple(cand: pd.DataFrame, lam: float, purse: float | None = None) -> pd.Series:
    """max sum(value*x) - lam*sum(cost*x) s.t. purse, min spend, squad size,
    overseas cap and role minimums. Same model as the Excel Solver sheet."""
    R = rules()
    c = R["common"]
    purse = purse or R["modes"]["mini_2027"]["purse_lakh"]["value"]
    need = assumptions()["strategy"]["role_min_counts"]["value"]
    prob = pulp.LpProblem("solver_mirror", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in cand.index}
    cost = pulp.lpSum(cand.at[i, "cost_lakh"] * x[i] for i in x)
    prob += pulp.lpSum(cand.at[i, "value"] * x[i] for i in x) - lam * cost
    prob += cost <= purse
    prob += cost >= c["min_spend_pct"]["value"] * purse
    prob += pulp.lpSum(x.values()) >= c["squad_min"]["value"]
    prob += pulp.lpSum(x.values()) <= c["squad_max"]["value"]
    prob += pulp.lpSum(x[i] for i in x if cand.at[i, "is_overseas"]) <= c["overseas_max"]["value"]
    for r in ROLES:
        holders = [i for i in x if r in cand.at[i, "roles"]]
        if len(holders) >= need.get(r, 0):  # same rule as the workbook
            prob += pulp.lpSum(x[i] for i in holders) >= need.get(r, 0)
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    return pd.Series({i: int(round(x[i].value() or 0)) for i in x})

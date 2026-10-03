"""Final recommendations table: Buy / Retain / Release with bid ceilings.

| Player | Action | Role | Impact | Fair value | Bid ceiling | Rationale | Risk | Backup |

* Bid ceiling = fair value x (1 + strategic premium of the gap the player fills)
* Every rationale cites a number; every Buy has a same-role backup that costs
  no more than the target's bid ceiling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import assumptions
from .optimiser import OptimiserResult


def _cr(lakh: float | None) -> str:
    return "n/a" if lakh is None or pd.isna(lakh) else f"Rs {lakh / 100:.2f} cr"


def _role_rank(player: str, role: str | None, league_long: pd.DataFrame) -> tuple[int | None, int | None]:
    if role is None:
        return None, None
    r = league_long[(league_long["player"] == player) & (league_long["role"] == role)]
    if r.empty:
        return None, None
    return int(r["league_rank"].iloc[0]), int(r["players_in_role"].iloc[0])


def _gap_status(roles: list[str], coverage: pd.DataFrame) -> str:
    st = coverage.set_index("role")["status"]
    statuses = [st.get(r, "Green") for r in roles]
    for s in ("Red", "Amber"):
        if s in statuses:
            return s
    return "Green"


def _risk(row: pd.Series) -> str:
    risks = []
    if pd.notna(row.get("age_at_auction")) and row["age_at_auction"] >= 33:
        risks.append(f"age {row['age_at_auction']:.0f}")
    if pd.notna(row.get("availability")) and row["availability"] < 0.6:
        risks.append(f"played {row['availability']:.0%} of team games in 3 yrs")
    if pd.notna(row.get("consistency_sd")) and pd.notna(row.get("impact")) and row["consistency_sd"] > max(2.0, abs(row["impact"]) * 1.5):
        risks.append(f"volatile (season-to-season SD {row['consistency_sd']:.1f})")
    balls = (row.get("balls_faced_3y") or 0) + (row.get("balls_bowled_3y") or 0)
    if not row.get("has_impact", False):
        risks.append("no recent IPL data")
    elif balls < 300:
        risks.append(f"small sample ({int(balls)} balls)")
    if row.get("projected_release", False) and row.get("action") in ("Buy", "Buy back"):
        risks.append(f"only available if {row['current_team']} release him (projected)")
    if row.get("is_overseas", False):
        risks.append("overseas: international clashes")
    return "; ".join(risks) if risks else "Low: regular, consistent performer"


def build_recommendations(res: OptimiserResult, players: pd.DataFrame, coverage: pd.DataFrame,
                          league_long: pd.DataFrame, pool_mask: pd.Series) -> pd.DataFrame:
    A = assumptions()["strategy"]
    premium = A["strategic_premium"]["value"]
    mode = res.params["mode"]
    fv_col = f"fair_value_{mode}"
    rows = []
    sel = pd.concat([res.squad, res.released])
    pool = players[pool_mask & ~players["player"].isin(sel["player"])].copy()
    pool_cost = pool[fv_col].fillna(30) * (1 + res.params["rival_inflation"])

    for _, r in sel.iterrows():
        role = r.get("primary_role")
        rank, n_role = _role_rank(r["player"], role, league_long)
        gap = _gap_status(r["roles"], coverage)
        fv = r.get(fv_col)
        ceiling = fv * (1 + premium[gap]) if pd.notna(fv) else np.nan
        imp = r.get("impact")
        rank_txt = f"#{rank} of {n_role} {role.lower()}s" if rank else "no ranked role"
        imp_txt = f"{imp:+.1f} runs/match" if pd.notna(imp) else "no recent data"
        action = r["action"]
        if action in ("Buy", "Buy back"):
            fills = f"; fills {gap} gap" if gap != "Green" else ""
            rationale = f"{rank_txt} ({imp_txt}); fair value {_cr(fv)}{fills}"
            cost = r.get("cost_lakh")
            if pd.notna(ceiling) and pd.notna(cost) and cost > ceiling:
                rationale += (f". Likely price {_cr(cost)} is above our ceiling: "
                              f"bid only up to {_cr(ceiling)}, else take the backup")
        elif action == "Retain" and mode == "mega_2028":
            price = r.get(f"expected_price_{mode}")
            rationale = (f"{rank_txt} ({imp_txt}); retention slot costs ~{_cr(r.get('cost_lakh'))} "
                         f"vs likely auction price {_cr(price)}")
        elif action == "Retain":
            sal = r.get("current_salary_lakh")
            cmp = ("below" if pd.notna(sal) and pd.notna(fv) and sal < fv else "above")
            rationale = f"{rank_txt} ({imp_txt}); salary {_cr(sal)} is {cmp} fair value {_cr(fv)}"
        else:  # Release
            sal = r.get("current_salary_lakh")
            rationale = (f"{imp_txt}, {rank_txt}; salary {_cr(sal)} vs fair value {_cr(fv)} "
                         f"- frees {_cr(sal)} of purse")
        backup = ""
        if action in ("Buy", "Buy back") and role:
            cand = pool[pool["roles"].apply(lambda rl: role in rl) & (pool_cost <= (ceiling if pd.notna(ceiling) else 1e9))]
            if len(cand):
                b = cand.sort_values("impact", ascending=False).iloc[0]
                backup = f"{b['display_name']} ({b['impact']:+.1f}, ~{_cr(pool_cost[b.name])})"
            else:
                backup = "none within ceiling - prioritise this bid"
        rows.append({
            "player": r["display_name"], "cricsheet_name": r["player"], "action": action,
            "role": role, "all_roles": ", ".join(r["roles"]), "overseas": bool(r.get("is_overseas", False)),
            "age": r.get("age_at_auction"), "impact_score": None if pd.isna(imp) else round(imp, 2),
            "fair_value_cr": None if pd.isna(fv) else round(fv / 100, 2),
            "expected_cost_cr": None if action == "Release" else round((r.get("cost_lakh") or 0) / 100, 2),
            "bid_ceiling_cr": None if action not in ("Buy", "Buy back") or pd.isna(ceiling) else round(ceiling / 100, 2),
            "gap_filled": gap if action in ("Buy", "Buy back") else None,
            "starter": bool(r.get("starter", False)),
            "rationale": rationale, "risk": _risk(r), "backup_option": backup,
        })
    order = {"Buy": 0, "Buy back": 1, "Retain": 2, "Release": 3}
    out = pd.DataFrame(rows)
    out["_o"] = out["action"].map(order)
    return out.sort_values(["_o", "starter", "impact_score"], ascending=[True, False, False]).drop(columns="_o").reset_index(drop=True)

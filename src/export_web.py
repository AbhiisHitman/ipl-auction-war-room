"""Export compact JSON for the React app (web/public/data/).

    python -m src.export_web
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from .config import PROCESSED_DIR, ROOT, assumptions, rules
from .economics import default_inputs, scenario_table
from .teams import active_codes, full_name

OUT = ROOT / "web" / "public" / "data"


def _clean(o):
    """Make pandas / numpy values JSON-safe (NaN -> None)."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if (o is None or math.isnan(o)) else round(float(o), 4)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if o is pd.NA or o is pd.NaT:
        return None
    return o


def _records(df: pd.DataFrame) -> list[dict]:
    return _clean(df.replace({np.nan: None}).to_dict(orient="records"))


def _write(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(_clean(obj), separators=(",", ":")))


def main() -> None:
    players = pd.read_csv(PROCESSED_DIR / "players.csv")
    briefs = json.loads((PROCESSED_DIR / "team_briefs.json").read_text())
    cov = pd.read_csv(PROCESSED_DIR / "coverage.csv")
    recs = pd.read_csv(PROCESSED_DIR / "recommendations.csv")
    summ = pd.read_csv(PROCESSED_DIR / "optimiser_summary.csv")
    scen = pd.read_csv(PROCESSED_DIR / "scenarios.csv") if (PROCESSED_DIR / "scenarios.csv").exists() else pd.DataFrame()
    homes = pd.read_csv(PROCESSED_DIR / "home_venues.csv").set_index("team")["venue"]
    venues = pd.read_csv(PROCESSED_DIR / "venue_profiles.csv").set_index("venue")
    table = pd.read_csv(PROCESSED_DIR / "league_table_2026.csv").set_index("team")
    fit = pd.read_csv(PROCESSED_DIR / "player_team_fit.csv")
    market = json.loads((PROCESSED_DIR / "market_model.json").read_text())
    win = json.loads((PROCESSED_DIR / "win_model.json").read_text())

    # ---------------- meta ----------------
    R = rules()
    _write("meta", {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "data_to": "2026-05-31",
        "market": market, "win_model": win,
        "modes": {m: {"label": c["label"], "purse_cr": c["purse_lakh"]["value"] / 100,
                      "purse_status": c["purse_lakh"]["status"]} for m, c in R["modes"].items()},
        "rules": {k: v["value"] for k, v in R["common"].items()},
        "mispricing_by_role": _records(pd.read_csv(PROCESSED_DIR / "mispricing_by_role.csv")),
        "mispricing_by_phase": _records(pd.read_csv(PROCESSED_DIR / "mispricing_by_phase.csv")),
        "role_min_counts": assumptions()["strategy"]["role_min_counts"]["value"],
    })

    # ---------------- teams ----------------
    teams = {}
    for t in active_codes():
        venue = homes[t]
        sal = players.loc[players["current_team"].eq(t), "current_salary_lakh"].sum() / 100
        inp = default_inputs(t, venue, salary_cr=sal)
        econ = scenario_table(inp)
        squad = players[players["current_team"].eq(t)].sort_values("impact", ascending=False)
        teams[t] = {
            "code": t, "name": full_name(t), "brief": briefs[t],
            "league_2026": table.loc[t].to_dict() if t in table.index else None,
            "venue_profile": venues.loc[venue].to_dict() if venue in venues.index else None,
            "coverage": _records(cov[cov["team"] == t].drop(columns="team")),
            "squad": _records(squad[["player", "display_name", "impact", "primary_role", "roles", "current_salary_lakh",
                                     "age_at_auction", "overseas", "capped", "fair_value_mini_2027"]]),
            "summary": _records(summ[summ["team"] == t]),
            "scenarios": _records(scen[scen["team"] == t]) if len(scen) else [],
            "recommendations": {m: _records(recs[(recs["team"] == t) & (recs["mode"] == m)].drop(columns=["team", "mode"]))
                                for m in ("mini_2027", "mega_2028")},
            "economics": {"inputs": {k: v for k, v in inp.items() if not isinstance(v, dict)},
                          "table": _records(econ)},
        }
    _write("teams", teams)

    # ---------------- players (+ top team fits) ----------------
    cols = ["player", "display_name", "current_team", "impact", "bat_impact", "bowl_impact", "impact_Powerplay",
            "impact_Middle", "impact_Death", "consistency_sd", "availability", "matches_3y", "primary_role", "roles",
            "phase_specialism", "age_at_auction", "overseas", "capped", "nationality", "bowling_style",
            "current_salary_lakh", "fair_value_mini_2027", "expected_price_mini_2027", "fair_value_mega_2028",
            "expected_price_mega_2028", "has_impact", "retired", "projected_release"]
    p = players[cols].copy()
    p = p[~p["retired"]]
    fits = {k: _records(g.sort_values("fit_rank").drop(columns="player")) for k, g in fit.groupby("player")}
    recs_p = _records(p)
    for r in recs_p:
        r["fit"] = fits.get(r["player"], [])
    _write("players", recs_p)

    # ---------------- market scatter ----------------
    t = pd.read_csv(PROCESSED_DIR / "market_training.csv")
    _write("market", _records(t[["season", "player_name", "team", "impact", "sold_price_lakh", "fair_value_lakh",
                                 "mispricing_pct", "overseas", "capped", "primary_role", "phase_specialism"]]))
    print("exported to", OUT)


if __name__ == "__main__":
    main()

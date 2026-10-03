"""Load everything the app / API needs from data/processed/ (no re-computation).

The API calls the same `run_team` and economics functions as the pipeline, so
web results always match the Python and Excel outputs.
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from .config import PROCESSED_DIR
from .impact_model import WinModel


def _roles(s) -> list[str]:
    return [r for r in str(s).split(";") if r and r != "nan"]


@lru_cache(maxsize=1)
def load_context() -> dict:
    players = pd.read_csv(PROCESSED_DIR / "players.csv")
    players["roles"] = players["roles"].apply(_roles)
    for c in ("overseas", "capped"):
        players[c] = players[c].astype("boolean")
    for c in ("has_impact", "retired", "projected_release"):
        players[c] = players[c].fillna(False).astype(bool)
    briefs = json.loads((PROCESSED_DIR / "team_briefs.json").read_text())
    wm_json = json.loads((PROCESSED_DIR / "win_model.json").read_text())
    s = wm_json["structural: win_pct = a + b * realised_impact"]
    r = wm_json["realisation: realised = c + rho * planned_strength"]
    wm = WinModel(a=s["a"], b=s["b"], c=r["c"], rho=r["rho"], r2_structural=s["r2"],
                  r2_realisation=r["r2"], n=wm_json["n_team_seasons"],
                  playoff_wins_threshold=wm_json["playoff_wins_threshold"], data=pd.DataFrame())
    from .config import assumptions
    q = assumptions()["strategy"]["replacement_level_percentile"]["value"]
    repl = float(players.loc[players["has_impact"], "impact"].quantile(q))
    from .planner import PLAN_SEASON
    league_long = pd.read_csv(PROCESSED_DIR / "league_role_rankings.csv")
    return {
        "players": players, "briefs": briefs, "win_model": wm,
        "role_weights": {t: b["role_weights"] for t, b in briefs.items()},
        "homes": pd.read_csv(PROCESSED_DIR / "home_venues.csv"),
        "coverage": pd.read_csv(PROCESSED_DIR / "coverage.csv"),
        "league_long": league_long, "repl": {PLAN_SEASON: repl},
    }

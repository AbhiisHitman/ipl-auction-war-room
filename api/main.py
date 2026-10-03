"""Auction War Room API - live optimiser and P&L for the React app.

    .venv/bin/uvicorn api.main:app --port 8000

Uses exactly the same functions as the pipeline (src/), so numbers match the
Excel models and processed tables.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.app_context import load_context
from src.economics import default_inputs, expected_profit, scenario_table
from src.pipeline import run_team
from src.recommend import build_recommendations
from src.teams import active_codes

app = FastAPI(title="IPL Auction War Room API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if math.isnan(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if o is pd.NA:
        return None
    return o


class OptimiseRequest(BaseModel):
    team: str
    mode: str = Field("mini_2027", pattern="^(mini_2027|mega_2028)$")
    strategy: str = Field("win_now", pattern="^(win_now|long_term)$")
    rival_inflation: float = Field(0.10, ge=0, le=1)
    locked: list[str] = []
    excluded: list[str] = []


class EconomicsRequest(BaseModel):
    team: str
    overrides: dict[str, float] = {}
    p_playoffs: float | None = None


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/optimise")
def optimise(req: OptimiseRequest):
    if req.team not in active_codes():
        raise HTTPException(404, "unknown team")
    ctx = load_context()
    out = run_team(ctx, req.team, req.mode, req.strategy, req.rival_inflation, req.locked, req.excluded)
    cov = ctx["coverage"][ctx["coverage"]["team"] == req.team]
    rec = build_recommendations(out["result"], ctx["players"], cov, ctx["league_long"], out["pool_mask"])
    res = out["result"]
    return _clean({
        "summary": out["summary"],
        "role_counts": res.role_counts.to_dict(orient="records"),
        "recommendations": rec.replace({np.nan: None}).to_dict(orient="records"),
        "params": res.params,
    })


@app.post("/api/economics")
def economics(req: EconomicsRequest):
    if req.team not in active_codes():
        raise HTTPException(404, "unknown team")
    ctx = load_context()
    venue = ctx["homes"].set_index("team").loc[req.team, "venue"]
    players = ctx["players"]
    sal = players.loc[players["current_team"].eq(req.team), "current_salary_lakh"].sum() / 100
    inp = default_inputs(req.team, venue, salary_cr=sal)
    for k, v in req.overrides.items():
        if k in inp and not isinstance(inp[k], dict):
            inp[k] = v
    p = req.p_playoffs if req.p_playoffs is not None else 0.5
    return _clean({
        "table": scenario_table(inp).to_dict(orient="records"),
        "expected": expected_profit(inp, p, 0.25),
        "inputs": {k: v for k, v in inp.items() if not isinstance(v, dict)},
    })

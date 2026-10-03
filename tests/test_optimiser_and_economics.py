"""Optimiser always respects the rules; economics arithmetic is consistent.

These tests use the processed data from `python -m src.pipeline --fast`.
"""
import json

import pandas as pd
import pytest

from src.config import PROCESSED_DIR
from src.economics import SCENARIOS, default_inputs, expected_profit, pnl
from src.optimiser import check_constraints, optimise

pytestmark = pytest.mark.skipif(not (PROCESSED_DIR / "players.csv").exists(),
                                reason="run `python -m src.pipeline --fast` first")


@pytest.fixture(scope="module")
def ctx():
    players = pd.read_csv(PROCESSED_DIR / "players.csv")
    players["roles"] = players["roles"].fillna("").apply(lambda s: [r for r in s.split(";") if r])
    for c in ("overseas", "capped"):
        players[c] = players[c].astype("boolean")
    briefs = json.loads((PROCESSED_DIR / "team_briefs.json").read_text())
    return players, briefs


def _pool(players, team, mode):
    alive = ~players["retired"] & players["overseas"].notna()
    if mode == "mini_2027":
        return alive & (players["current_team"].isna() | players["projected_release"])
    return alive & players["current_team"].ne(team)


@pytest.mark.parametrize("team", ["CSK", "MI", "RCB", "SRH", "LSG"])
@pytest.mark.parametrize("mode", ["mini_2027", "mega_2028"])
def test_constraints_hold(ctx, team, mode):
    players, briefs = ctx
    res = optimise(players, team, mode, briefs[team]["role_weights"], "win_now",
                   pool_filter=_pool(players, team, mode))
    assert res.status == "Optimal"
    checks = check_constraints(res)
    assert all(checks.values()), checks


def test_mega_retention_limits(ctx):
    players, briefs = ctx
    res = optimise(players, "RCB", "mega_2028", briefs["RCB"]["role_weights"], "win_now",
                   pool_filter=_pool(players, "RCB", "mega_2028"))
    kept = res.squad[res.squad["action"] == "Retain"]
    assert len(kept) <= 6
    assert int((~kept["is_capped"]).sum()) <= 2
    assert int(kept["is_capped"].sum()) <= 5


def test_locks_and_exclusions(ctx):
    players, briefs = ctx
    pool = _pool(players, "DC", "mini_2027")
    cand = players[pool & players["has_impact"]].sort_values("impact", ascending=False)
    lock = cand["player"].iloc[3]
    best = cand["player"].iloc[0]
    res = optimise(players, "DC", "mini_2027", briefs["DC"]["role_weights"], "win_now",
                   locked=[lock], excluded=[best], pool_filter=pool)
    names = set(res.squad["player"])
    assert lock in names
    assert best not in names
    assert all(check_constraints(res).values())


def test_higher_inflation_never_lowers_cost_of_same_squad(ctx):
    players, briefs = ctx
    pool = _pool(players, "PBKS", "mini_2027")
    lo = optimise(players, "PBKS", "mini_2027", briefs["PBKS"]["role_weights"], "win_now", 0.1, pool_filter=pool)
    hi = optimise(players, "PBKS", "mini_2027", briefs["PBKS"]["role_weights"], "win_now", 0.3, pool_filter=pool)
    # Squad strength can only fall (or stay) when every price rises.
    assert hi.strength_after <= lo.strength_after + 1e-6


def test_pnl_totals_add_up():
    inp = default_inputs("RCB", "M Chinnaswamy Stadium, Bengaluru", salary_cr=120)
    t = pnl(inp, "won_title").set_index("line")["value_cr"]
    rev_lines = ["Central media rights share", "Central sponsorship share", "Team sponsorships",
                 "Ticketing (home matches)", "Merchandise", "Prize money"]
    assert t["Total revenue"] == pytest.approx(t[rev_lines].sum())
    assert t["Operating profit"] == pytest.approx(t["Total revenue"] - t["Total operating costs"])
    # Central media share = 48,390 / 5 * 50% / 10
    assert t["Central media rights share"] == pytest.approx(48390 / 5 * 0.5 / 10)


def test_title_beats_playoffs_beats_missing():
    inp = default_inputs("PBKS", "Maharaja Yadavindra Singh Stadium, Mullanpur")
    rev = [pnl(inp, s).set_index("line").loc["Total revenue", "value_cr"] for s in SCENARIOS]
    assert rev[0] < rev[1] < rev[2]


def test_expected_profit_probabilities_sum_to_one():
    inp = default_inputs("MI", "Wankhede Stadium, Mumbai")
    e = expected_profit(inp, p_playoffs=0.6, p_title_given_playoffs=0.25)
    assert e["p_missed_playoffs"] + e["p_made_playoffs"] + e["p_won_title"] == pytest.approx(1.0)

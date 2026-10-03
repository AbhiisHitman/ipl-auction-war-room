"""Franchise P&L (Python mirror of outputs/excel/franchise_model.xlsx).

Every line uses the same formula as the Excel 'P&L' sheet, so the app's
sliders and the spreadsheet give identical answers for the same inputs.
All money in INR crore per season.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .config import assumptions, rules

SCENARIOS = ["missed_playoffs", "made_playoffs", "won_title"]


def default_inputs(team: str, home_venue: str, salary_cr: float | None = None) -> dict[str, Any]:
    """Flatten assumptions.yaml into the scalar inputs for one team."""
    e = assumptions()["economics"]
    brand = e["brand_value_usd_m"]["value"]
    avg_brand = sum(brand.values()) / len(brand)
    return {
        "team": team,
        "media_rights_total_cr": e["media_rights_total_cr"]["value"],
        "media_rights_seasons": e["media_rights_seasons"]["value"],
        "franchise_share_media_rights": e["franchise_share_media_rights"]["value"],
        "title_sponsorship_cr": e["title_sponsorship_cr_per_season"]["value"],
        "other_central_sponsorship_cr": e["other_central_sponsorship_cr_per_season"]["value"],
        "franchise_share_central_sponsorship": e["franchise_share_central_sponsorship"]["value"],
        "n_teams": e["n_teams"]["value"],
        "brand_index": brand[team] / avg_brand,
        "team_sponsorship_base_cr": e["team_sponsorship_base_cr"]["value"],
        "merchandise_base_cr": e["merchandise_base_cr"]["value"],
        "home_matches": e["home_matches"]["value"],
        "capacity": e["stadium_capacity"]["value"].get(home_venue, 40000),
        "max_sellable_seats": e["max_sellable_seats"]["value"],
        "occupancy": e["occupancy"]["value"],
        "complimentary_share": e["complimentary_share"]["value"],
        "avg_ticket_price_inr": e["avg_ticket_price_inr"]["value"],
        "match_day_cost_cr": e["match_day_cost_cr_per_home_match"]["value"],
        "player_salary_cr": e["player_salary_cr"]["value"] if salary_cr is None else salary_cr,
        "match_fee_lakh": rules()["common"]["match_fee_lakh"]["value"],
        "match_fee_players": e["match_fee_players_per_match"]["value"],
        "league_matches": rules()["common"]["league_matches_per_team"]["value"],
        "support_staff_cr": e["support_staff_cr"]["value"],
        "operations_admin_cr": e["operations_admin_cr"]["value"],
        "marketing_cr": e["marketing_cr"]["value"],
        "travel_cr": e["travel_cr"]["value"],
        "bcci_fee_share": e["bcci_fee_share_of_team_revenue"]["value"],
        "franchise_fee_cr": e["franchise_fee_cr_per_season"]["value"][team],
        "prize": e["prize_money_cr"]["value"],
        "sponsorship_uplift": e["sponsorship_uplift"]["value"],
        "merchandise_uplift": e["merchandise_uplift"]["value"],
    }


# Average prize for a playoff team that does not win: (runner-up + 3rd + 4th) / 3.
def _prize(inp: dict, scenario: str) -> float:
    p = inp["prize"]
    if scenario == "won_title":
        return p["winner"]
    if scenario == "made_playoffs":
        return (p["runner_up"] + p["third"] + p["fourth"]) / 3
    return p["other"]


def _playoff_games(scenario: str) -> float:
    # Expected extra matches: a non-winning playoff team plays ~2 (1-3); the winner 2-3.
    return {"missed_playoffs": 0.0, "made_playoffs": 2.0, "won_title": 2.5}[scenario]


def pnl(inp: dict, scenario: str = "missed_playoffs") -> pd.DataFrame:
    """Return the P&L as a tidy table of (section, line, value_cr)."""
    central_media = inp["media_rights_total_cr"] / inp["media_rights_seasons"] * inp["franchise_share_media_rights"] / inp["n_teams"]
    central_spons = (inp["title_sponsorship_cr"] + inp["other_central_sponsorship_cr"]) * inp["franchise_share_central_sponsorship"] / inp["n_teams"]
    team_spons = inp["team_sponsorship_base_cr"] * inp["brand_index"] * (1 + inp["sponsorship_uplift"][scenario])
    seats = min(inp["capacity"], inp["max_sellable_seats"]) * inp["occupancy"] * (1 - inp["complimentary_share"])
    ticketing = inp["home_matches"] * seats * inp["avg_ticket_price_inr"] / 1e7
    merch = inp["merchandise_base_cr"] * inp["brand_index"] * (1 + inp["merchandise_uplift"][scenario])
    prize = _prize(inp, scenario)
    revenue = central_media + central_spons + team_spons + ticketing + merch + prize

    matches_played = inp["league_matches"] + _playoff_games(scenario)
    match_fees = inp["match_fee_lakh"] * inp["match_fee_players"] * matches_played / 100
    bcci_fee = inp["bcci_fee_share"] * (team_spons + merch)
    match_day = inp["match_day_cost_cr"] * inp["home_matches"]
    op_costs = (inp["player_salary_cr"] + match_fees + inp["support_staff_cr"] + inp["operations_admin_cr"]
                + inp["marketing_cr"] + inp["travel_cr"] + match_day + bcci_fee)
    op_profit = revenue - op_costs
    rows = [
        ("Revenue", "Central media rights share", central_media),
        ("Revenue", "Central sponsorship share", central_spons),
        ("Revenue", "Team sponsorships", team_spons),
        ("Revenue", "Ticketing (home matches)", ticketing),
        ("Revenue", "Merchandise", merch),
        ("Revenue", "Prize money", prize),
        ("Revenue", "Total revenue", revenue),
        ("Costs", "Player salaries", inp["player_salary_cr"]),
        ("Costs", "Match fees", match_fees),
        ("Costs", "Support staff", inp["support_staff_cr"]),
        ("Costs", "Operations & admin", inp["operations_admin_cr"]),
        ("Costs", "Marketing", inp["marketing_cr"]),
        ("Costs", "Travel", inp["travel_cr"]),
        ("Costs", "Match-day costs", match_day),
        ("Costs", "BCCI fee on team revenue", bcci_fee),
        ("Costs", "Total operating costs", op_costs),
        ("Profit", "Operating profit", op_profit),
        ("Profit", "Operating margin", op_profit / revenue if revenue else 0.0),
        ("Profit", "Franchise fee instalment (assumption)", inp["franchise_fee_cr"]),
        ("Profit", "Profit after franchise fee", op_profit - inp["franchise_fee_cr"]),
        ("Mix", "Central (fixed) share of revenue", (central_media + central_spons) / revenue if revenue else 0.0),
    ]
    return pd.DataFrame(rows, columns=["section", "line", "value_cr"])


def scenario_table(inp: dict) -> pd.DataFrame:
    """P&L side by side for the three performance scenarios."""
    out = None
    for s in SCENARIOS:
        t = pnl(inp, s).set_index(["section", "line"]).rename(columns={"value_cr": s})
        out = t if out is None else out.join(t)
    return out.reset_index()


def expected_profit(inp: dict, p_playoffs: float, p_title_given_playoffs: float) -> dict[str, float]:
    """Probability-weighted revenue and profit across the three scenarios."""
    p_title = p_playoffs * p_title_given_playoffs
    probs = {"missed_playoffs": 1 - p_playoffs, "made_playoffs": p_playoffs - p_title, "won_title": p_title}
    rev = prof = 0.0
    for s, p in probs.items():
        t = pnl(inp, s).set_index("line")["value_cr"]
        rev += p * t["Total revenue"]
        prof += p * t["Operating profit"]
    return {"expected_revenue_cr": rev, "expected_profit_cr": prof, **{f"p_{k}": v for k, v in probs.items()}}

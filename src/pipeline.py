"""End-to-end build: raw data -> every table in data/processed/.

    python -m src.pipeline            # full build (all 10 teams, both auction modes)
    python -m src.pipeline --fast     # skip the scenario sweep

The app and the Excel/deck builders only read what this writes.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from . import features as F
from . import market as M
from . import squad as S
from . import team_strategy as TS
from . import valuation as V
from .config import PROCESSED_DIR, RAW_DIR, assumptions, ensure_dirs, rules, valuation_params
from .economics import default_inputs, expected_profit
from .enrich import add_person_key, build_player_bios
from .impact_model import fit_win_model, realised_team_impact, team_season_strength, team_win_pct
from .ingest import build_interim, read_interim
from .planner import PLAN_SEASON, STANCE_TO_STRATEGY, flag_projected_releases, pools, run_team  # noqa: F401
from .player_fit import player_team_fit
from .player_map import build_player_map
from .players import build_players
from .recommend import build_recommendations
from .teams import active_codes
from .wiki_auction import build_auction_records, build_retired

MODES = {"mini_2027": pd.Timestamp("2026-12-15"), "mega_2028": pd.Timestamp("2027-12-01")}
WINDOW = [2024, 2025, 2026]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)


def roles_to_str(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["roles"] = out["roles"].apply(lambda r: ";".join(r) if isinstance(r, list) else "")
    return out


def build_data_layer() -> dict:
    """Phase 1: ingest, auction records, bios, name mapping."""
    log("Ingesting Cricsheet")
    build_interim()
    log("Parsing Wikipedia auction tables")
    auction = add_person_key(build_auction_records())
    retired = build_retired()
    save(auction, "auction")
    log("Player bios (Wikipedia, cached)")
    bios = build_player_bios(auction)
    matches, mp = read_interim("matches"), read_interim("match_players")
    pmap, report = build_player_map(auction, mp, matches)
    log(f"Player map: {report['matched_pct_with_history'].to_dict()}")
    return {"auction": auction, "bios": bios, "pmap": pmap, "retired": retired,
            "matches": matches, "match_players": mp}


def build_valuation(ctx: dict) -> dict:
    """Phase 3: Impact Scores (as of every season 2012-2027)."""
    log("Impact Scores")
    balls = F.add_phase(read_interim("balls"))
    matches, mp = ctx["matches"], ctx["match_players"]
    p = valuation_params()
    rain = set(matches.loc[matches["rain_affected"], "match_id"]) if p["exclude_rain_affected_from_baseline"] else set()
    base = V.phase_baselines(balls, rain)
    wv = V.wicket_values(balls)
    apps = F.appearances(mp, matches)
    season, phase_tab = V.season_impact(F.batting_table(balls), F.bowling_table(balls), apps, base, wv)
    impact_by_season = {y: V.weighted_impact(season, phase_tab, y) for y in range(2012, PLAN_SEASON + 1)}
    win_now = V.weighted_impact(season, phase_tab, PLAN_SEASON, p["recency_weights_win_now"])

    save(base, "phase_baselines")
    save(wv.rename("wicket_value_runs").reset_index(), "wicket_values")
    save(season, "player_season_impact")
    save(pd.concat(impact_by_season.values(), ignore_index=True), "impact_history")
    ctx.update(balls=balls, apps=apps, season=season, phase_tab=phase_tab,
               impact_by_season=impact_by_season, win_now=win_now, wicket_values=wv)
    return ctx


def build_player_table(ctx: dict) -> dict:
    """Roles + master table + market model + fair values."""
    log("Roles and player master")
    balls, apps, bios, pmap = ctx["balls"], ctx["apps"], ctx["bios"], ctx["pmap"]
    positions = F.batting_positions(balls)
    feat = S.role_features(balls, positions, WINDOW)
    link = pmap.dropna(subset=["cricsheet_name"]).set_index("cricsheet_name")["person"]
    btype = link.map(bios.set_index("person")["bowling_type"])
    kflag = link.map(bios.set_index("person")["wiki_role"].fillna("").str.contains("keeper", case=False))
    # Auction-listed keepers count too.
    a_keep = ctx["auction"].loc[ctx["auction"]["role"].eq("Wicket-keeper"), "person"].unique()
    kflag = kflag | link.isin(a_keep)
    mwin = apps[apps["season"].isin(WINDOW)].groupby("player")["matches"].sum()
    roles = S.classify_roles(feat, btype, kflag, mwin)
    avail = V.availability(apps, F.team_matches(ctx["matches"]), PLAN_SEASON)

    impact = ctx["impact_by_season"][PLAN_SEASON]
    players = build_players(ctx["auction"], pmap, bios, impact, roles, avail, MODES["mini_2027"])
    players = players.merge(ctx["win_now"][["player", "impact"]].rename(columns={"impact": "impact_win_now"}),
                            on="player", how="left")
    players["primary_role"] = players.apply(S.primary_role, axis=1)
    players["phase_specialism"] = np.where(players["has_impact"], M.phase_specialism(players.fillna(
        {"impact_Powerplay": 0, "impact_Middle": 0, "impact_Death": 0})), None)
    retired = set(ctx["retired"]["player_name"]) | set(ctx["retired"]["wiki_title"].dropna())
    players["retired"] = players["person"].isin(retired) | players["display_name"].isin(retired)

    league_long = S.league_role_rankings(players[players["has_impact"]])

    log("Market model")
    train = M.training_set(ctx["auction"], pmap, {y: ctx["impact_by_season"][y] for y in range(2022, 2027)})
    model = M.fit_market_model(train)
    t = model.train
    t["phase_specialism"] = M.phase_specialism(t)
    t = t.merge(players[["player", "primary_role"]], on="player", how="left")
    price_model = M.fit_market_model(train, M.PRICE_FORMULA)
    for mode in MODES:
        players[f"fair_value_{mode}"] = M.fair_values_for_auction(model, players, mode)
        players[f"expected_price_{mode}"] = M.expected_prices_for_auction(price_model, players, mode)
    players.loc[~players["has_impact"], [f"fair_value_{m}" for m in MODES] + [f"expected_price_{m}" for m in MODES]] = np.nan

    save(roles_to_str(players), "players")
    save(league_long, "league_role_rankings")
    save(t, "market_training")
    save(M.mispricing_by_group(t.dropna(subset=["primary_role"]), "primary_role").reset_index(), "mispricing_by_role")
    save(M.mispricing_by_group(t, "phase_specialism").reset_index(), "mispricing_by_phase")
    model.summary_table().reset_index().rename(columns={"index": "term"}).to_csv(PROCESSED_DIR / "market_model_coefficients.csv", index=False)
    price_model.summary_table().reset_index().rename(columns={"index": "term"}).to_csv(PROCESSED_DIR / "price_model_coefficients.csv", index=False)
    insights = M.top_insights(t, model)
    (PROCESSED_DIR / "market_model.json").write_text(json.dumps({
        "formula": "log(price_lakh) ~ impact + overseas + capped + C(season)",
        "n": int(model.fit.nobs), "r2": round(model.fit.rsquared, 3), "adj_r2": round(model.fit.rsquared_adj, 3),
        "smearing_factor_not_applied": round(model.smearing, 3), "insights": insights,
        "price_model": {"formula": M.PRICE_FORMULA, "r2": round(price_model.fit.rsquared, 3),
                        "adj_r2": round(price_model.fit.rsquared_adj, 3)}}, indent=2))
    ctx.update(players=players, league_long=league_long, market=model)
    return ctx


def build_teams(ctx: dict) -> dict:
    """Squad gaps, venues, priorities per team."""
    log("Squad gaps and team strategy")
    players, matches, balls = ctx["players"], ctx["matches"], ctx["balls"]
    homes = F.home_venues(matches, [2026])
    btype = players.set_index("player")["bowling_type"]
    venues = F.venue_profiles(balls, btype, WINDOW)
    table = TS.league_table(matches, 2026)
    save(homes, "home_venues")
    save(venues, "venue_profiles")
    save(table, "league_table_2026")

    cov_all, briefs, weights = [], {}, {}
    R = rules()
    for team in active_codes():
        sq = players[players["current_team"].eq(team)]
        cov = S.coverage_matrix(sq, ctx["league_long"])
        cov.insert(0, "team", team)
        cov_all.append(cov)
        venue = homes.loc[homes["team"] == team, "venue"].iloc[0]
        prof = venues[venues["venue"] == venue].iloc[0] if (venues["venue"] == venue).any() else None
        w = TS.role_weights(cov, TS.venue_multipliers(prof))
        weights[team] = w
        purse_left = R["modes"]["mini_2027"]["purse_lakh"]["value"] - sq["current_salary_lakh"].sum()
        ov_left = R["common"]["overseas_max"]["value"] - int(sq["overseas"].fillna(False).sum())
        finish = table.set_index("team").loc[team]
        briefs[team] = TS.team_brief(team, cov, w, venue, prof, finish, sq, purse_left, ov_left)
    save(pd.concat(cov_all, ignore_index=True), "coverage")
    (PROCESSED_DIR / "team_briefs.json").write_text(json.dumps(briefs, indent=2, default=str))
    ctx.update(homes=homes, venues=venues, briefs=briefs, role_weights=weights, league_table=table)
    return ctx


def build_impact_model(ctx: dict) -> dict:
    log("Win model (squad strength -> win %)")
    repl = {s: float(i["impact"].quantile(assumptions()["strategy"]["replacement_level_percentile"]["value"]))
            for s, i in ctx["impact_by_season"].items()}
    seasons = {s: i for s, i in ctx["impact_by_season"].items() if 2012 <= s <= 2026}
    strength = team_season_strength(ctx["apps"], seasons, repl)
    realised = realised_team_impact(ctx["apps"], ctx["season"], F.team_matches(ctx["matches"]))
    model = fit_win_model(strength, team_win_pct(ctx["matches"]), ctx["matches"], realised)
    save(model.data, "team_strength")
    (PROCESSED_DIR / "win_model.json").write_text(json.dumps({
        "structural: win_pct = a + b * realised_impact": {"a": round(model.a, 4), "b": round(model.b, 5),
                                                          "r2": round(model.r2_structural, 3)},
        "realisation: realised = c + rho * planned_strength": {"c": round(model.c, 3), "rho": round(model.rho, 3),
                                                              "r2": round(model.r2_realisation, 3)},
        "win_pct_per_run_of_planned_strength": round(model.slope, 5),
        "n_team_seasons": model.n, "playoff_wins_threshold": model.playoff_wins_threshold}, indent=2))
    ctx.update(win_model=model, repl=repl)
    return ctx


def build_recommendations_all(ctx: dict, scenarios: bool = True) -> dict:
    players = flag_projected_releases(ctx["players"])
    ctx["players"] = players
    save(roles_to_str(players), "players")
    recs, summaries, scen = [], [], []
    for mode in MODES:
        for team in active_codes():
            stance = STANCE_TO_STRATEGY[ctx["briefs"][team]["stance"]]
            out = run_team(ctx, team, mode, stance)
            cov = pd.read_csv(PROCESSED_DIR / "coverage.csv").query("team == @team")
            rec = build_recommendations(out["result"], players, cov, ctx["league_long"], out["pool_mask"])
            rec.insert(0, "mode", mode)
            rec.insert(0, "team", team)
            recs.append(rec)
            summaries.append(out["summary"])
            log(f"{mode} {team}: {out['summary']['status']} in {out['summary']['solve_seconds']}s, "
                f"strength {out['summary']['strength_before']} -> {out['summary']['strength_after']}")
            if scenarios:
                for strat in ("win_now", "long_term"):
                    for infl in assumptions()["strategy"]["rival_inflation_scenarios"]["value"]:
                        o = run_team(ctx, team, mode, strat, infl)["summary"]
                        o["scenario"] = f"{'Win Now' if strat == 'win_now' else 'Long-Term'} @ +{infl:.0%}"
                        scen.append(o)
    log("Player -> team fit")
    cov = pd.read_csv(PROCESSED_DIR / "coverage.csv")
    fit = player_team_fit(players, cov, ctx["briefs"], ctx["repl"][PLAN_SEASON], ctx["win_model"].slope)
    save(fit, "player_team_fit")
    save(pd.concat(recs, ignore_index=True), "recommendations")
    save(pd.DataFrame(summaries), "optimiser_summary")
    if scen:
        save(pd.DataFrame(scen), "scenarios")
    return ctx


def main(fast: bool = False) -> dict:
    ensure_dirs()
    ctx = build_data_layer()
    ctx = build_valuation(ctx)
    ctx = build_player_table(ctx)
    ctx = build_teams(ctx)
    ctx = build_impact_model(ctx)
    ctx = build_recommendations_all(ctx, scenarios=not fast)
    log("Done")
    return ctx


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="skip the scenario sweep")
    main(fast=ap.parse_args().fast)

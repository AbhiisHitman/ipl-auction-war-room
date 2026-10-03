"""Data-driven role classification and the squad role-coverage matrix.

Roles (a player can hold several; `primary_role` is the one he is most
valuable in):

Batting (>= 120 balls faced in the 3-season window)
  Opener        median batting position <= 2
  Anchor        median batting position 3-4
  Finisher      median position >= 5 AND >= 35% of balls faced in the Death phase
  Middle-order  median position >= 5 otherwise
  Wicketkeeper  >= 2 stumpings as fielder, or listed as keeper (Wikipedia)
Bowling (>= 120 legal balls bowled in the window)
  Death pacer      pace bowler with >= 30% of balls in the Death phase
  Powerplay pacer  other pace bowlers
  Wrist spinner / Finger spinner   from the bowling style on Wikipedia
All-rounder  >= 6 balls faced AND >= 12 balls bowled per match

Manual overrides: data/raw/role_overrides.csv (player, roles separated by ';').
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RAW_DIR, assumptions

ROLES = ["Opener", "Anchor", "Middle-order", "Finisher", "Wicketkeeper",
         "Powerplay pacer", "Death pacer", "Wrist spinner", "Finger spinner", "All-rounder"]
BATTING_ROLES = {"Opener", "Anchor", "Middle-order", "Finisher", "Wicketkeeper"}
BOWLING_ROLES = {"Powerplay pacer", "Death pacer", "Wrist spinner", "Finger spinner"}
ROLE_OVERRIDES = RAW_DIR / "role_overrides.csv"

MIN_BAT_BALLS = 120
MIN_BOWL_BALLS = 120
FINISHER_DEATH_SHARE = 0.35
DEATH_PACER_SHARE = 0.30


def role_features(balls: pd.DataFrame, positions: pd.DataFrame, window: list[int]) -> pd.DataFrame:
    """Per-player usage stats over the window: batting position, phase shares."""
    b = balls[balls["season"].isin(window)]
    pos = positions.merge(b[["match_id", "season"]].drop_duplicates(), on="match_id")
    med_pos = pos.groupby("player")["position"].median().rename("median_bat_pos")

    faced = b[b["ball_faced"]]
    bf = faced.groupby(["batter", "phase"]).size().unstack(fill_value=0)
    bf_tot = bf.sum(axis=1)
    bat = pd.DataFrame({"balls_faced_w": bf_tot,
                        "death_bat_share": bf.get("Death", 0) / bf_tot})
    bat.index.name = "player"

    bw = b.groupby(["bowler", "phase"])["legal_ball"].sum().unstack(fill_value=0)
    bw_tot = bw.sum(axis=1)
    bowl = pd.DataFrame({"balls_bowled_w": bw_tot,
                         "pp_bowl_share": bw.get("Powerplay", 0) / bw_tot,
                         "death_bowl_share": bw.get("Death", 0) / bw_tot})
    bowl.index.name = "player"

    stump = (b[b["wicket_kind"] == "stumped"].groupby("fielder_1").size().rename("stumpings"))
    stump.index.name = "player"
    out = pd.concat([med_pos, bat, bowl, stump], axis=1).fillna({"stumpings": 0})
    return out.reset_index().rename(columns={"index": "player"})


def classify_roles(feat: pd.DataFrame, bowling_type: pd.Series, keeper_flag: pd.Series,
                   matches: pd.Series) -> pd.DataFrame:
    """Return player -> roles (list) using the documented rules.

    bowling_type: player -> pace / wrist_spin / finger_spin (may be missing)
    keeper_flag:  player -> True if listed as a wicket-keeper on Wikipedia/auction
    matches:      player -> matches in the window"""
    f = feat.set_index("player").copy()
    f["bowling_type"] = bowling_type.reindex(f.index)
    f["keeper_listed"] = keeper_flag.reindex(f.index).fillna(False).astype(bool)
    f["matches_w"] = matches.reindex(f.index).fillna(1).clip(lower=1)

    roles: dict[str, list[str]] = {}
    for p, r in f.iterrows():
        rl: list[str] = []
        bats = r["balls_faced_w"] >= MIN_BAT_BALLS
        bowls = r["balls_bowled_w"] >= MIN_BOWL_BALLS
        if bats:
            pos = r["median_bat_pos"]
            if pos <= 2:
                rl.append("Opener")
            elif pos <= 4:
                rl.append("Anchor")
            elif r["death_bat_share"] >= FINISHER_DEATH_SHARE:
                rl.append("Finisher")
            else:
                rl.append("Middle-order")
        if (r["stumpings"] >= 2 or r["keeper_listed"]) and r["balls_faced_w"] >= 30:
            rl.append("Wicketkeeper")
        if bowls:
            bt = r["bowling_type"]
            if bt == "wrist_spin":
                rl.append("Wrist spinner")
            elif bt == "finger_spin":
                rl.append("Finger spinner")
            elif bt == "pace" or pd.isna(bt):
                # Unknown style: pace if he bowls in the powerplay/death like a seamer.
                if pd.isna(bt) and r["pp_bowl_share"] + r["death_bowl_share"] < 0.35:
                    rl.append("Finger spinner")
                elif r["death_bowl_share"] >= DEATH_PACER_SHARE:
                    rl.append("Death pacer")
                else:
                    rl.append("Powerplay pacer")
        if (r["balls_faced_w"] / r["matches_w"] >= 6) and (r["balls_bowled_w"] / r["matches_w"] >= 12):
            rl.append("All-rounder")
        roles[p] = rl

    out = pd.DataFrame({"player": list(roles.keys()), "roles": list(roles.values())})
    if ROLE_OVERRIDES.exists():
        ov = pd.read_csv(ROLE_OVERRIDES)
        ov_map = {r.player: [x.strip() for x in str(r.roles).split(";") if x.strip()] for r in ov.itertuples()}
        out["roles"] = [ov_map.get(p, rl) for p, rl in zip(out["player"], out["roles"])]
    return out


def role_impact(row: pd.Series, role: str) -> float:
    """The impact number that matters for a role: batting impact for batting
    roles, bowling impact for bowling roles, total for all-rounders."""
    if role in BATTING_ROLES:
        return row["bat_impact"]
    if role in BOWLING_ROLES:
        return row["bowl_impact"]
    return row["impact"]


def primary_role(row: pd.Series) -> str | None:
    rl = row["roles"]
    if not rl:
        return None
    if "All-rounder" in rl:
        return "All-rounder"
    return max(rl, key=lambda r: role_impact(row, r))


def league_role_rankings(players: pd.DataFrame) -> pd.DataFrame:
    """Long table: every player x role he holds, ranked within the league."""
    rows = []
    for _, r in players.iterrows():
        for role in r["roles"] or []:
            rows.append({"player": r["player"], "role": role, "role_impact": role_impact(r, role)})
    long = pd.DataFrame(rows)
    long["league_rank"] = long.groupby("role")["role_impact"].rank(ascending=False, method="first")
    long["players_in_role"] = long.groupby("role")["role"].transform("size")
    return long


def coverage_matrix(squad: pd.DataFrame, league_long: pd.DataFrame) -> pd.DataFrame:
    """Green / Amber / Red per role for one squad.

    For a role needing k players, look at the squad's k-th best player in that
    role and his league rank r: Green if r <= 10k, Amber if r <= 15k, else Red
    (Red too if the squad has fewer than k players for the role)."""
    a = assumptions()["strategy"]
    need = a["role_min_counts"]["value"]
    mult = a["coverage_rank_multiplier"]["value"]
    ranks = league_long.merge(squad[["player"]], on="player")
    rows = []
    for role in ROLES:
        k = int(need.get(role, 1))
        have = ranks[ranks["role"] == role].sort_values("role_impact", ascending=False)
        bench = league_long[league_long["role"] == role].sort_values("role_impact", ascending=False)
        green_cut = bench["role_impact"].iloc[min(len(bench), mult["green"] * k) - 1] if len(bench) else np.nan
        if len(have) < k:
            status, kth_rank, kth_val = "Red", np.nan, np.nan
            note = f"Only {len(have)} of {k} needed {role.lower()}(s) in the squad"
        else:
            kth = have.iloc[k - 1]
            kth_rank, kth_val = kth["league_rank"], kth["role_impact"]
            status = "Green" if kth_rank <= mult["green"] * k else ("Amber" if kth_rank <= mult["amber"] * k else "Red")
            note = (f"{'Best' if k == 1 else f'#{k}'} {role.lower()} ranks {int(kth_rank)} of "
                    f"{int(kth['players_in_role'])} in the league (starter level = top {mult['green'] * k})")
        rows.append({
            "role": role, "needed": k, "in_squad": len(have), "status": status,
            "kth_best_league_rank": kth_rank, "kth_best_role_impact": kth_val,
            "league_starter_benchmark": green_cut,
            "best_player": have["player"].iloc[0] if len(have) else None,
            "squad_players": ", ".join(have["player"].tolist()),
            "explanation": note,
        })
    return pd.DataFrame(rows)

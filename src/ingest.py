"""Load and clean raw data.

Cricsheet (csv2 format) -> three tidy tables in data/interim/:
  * matches.parquet        one row per match (season, venue, result, flags)
  * match_players.parquet  one row per player per match (the named XI / 12)
  * balls.parquet          one row per delivery

Auction data is parsed from Wikipedia in src/wiki_auction.py and loaded here
via `load_auction()` so every consumer goes through one entry point.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AUCTION_RAW_DIR, CRICSHEET_DIR, INTERIM_DIR, ensure_dirs
from .teams import team_code

CSV2_DIR = CRICSHEET_DIR / "ipl_csv2"

# Wicket kinds that are credited to the bowler (run outs etc. are not).
BOWLER_WICKETS = {"bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"}
# Dismissals that are not really "getting out" for valuation purposes.
NON_DISMISSALS = {"retired hurt", "retired not out"}

# Ground-name canonicalisation. Cricsheet spells the same ground several ways
# ("Wankhede Stadium" vs "Wankhede Stadium, Mumbai"); renamed grounds are merged.
VENUE_RULES: list[tuple[str, str]] = [
    (r"chinnaswamy", "M Chinnaswamy Stadium, Bengaluru"),
    (r"wankhede", "Wankhede Stadium, Mumbai"),
    (r"brabourne", "Brabourne Stadium, Mumbai"),
    (r"dy patil", "DY Patil Stadium, Navi Mumbai"),
    (r"eden gardens", "Eden Gardens, Kolkata"),
    (r"chidambaram|chepauk", "MA Chidambaram Stadium, Chennai"),
    (r"feroz shah kotla|arun jaitley", "Arun Jaitley Stadium, Delhi"),
    (r"narendra modi|sardar patel", "Narendra Modi Stadium, Ahmedabad"),
    (r"ekana|vajpayee", "Ekana Cricket Stadium, Lucknow"),
    (r"rajiv gandhi", "Rajiv Gandhi Intl Stadium, Hyderabad"),
    (r"sawai mansingh", "Sawai Mansingh Stadium, Jaipur"),
    (r"barsapara|guwahati", "Barsapara Stadium, Guwahati"),
    (r"yadavindra|mullanpur|new pca", "Maharaja Yadavindra Singh Stadium, Mullanpur"),
    (r"punjab cricket association|bindra|mohali", "PCA IS Bindra Stadium, Mohali"),
    (r"himachal|dharamsala|dharmasala", "HPCA Stadium, Dharamsala"),
    (r"maharashtra cricket association|gahunje", "MCA Stadium, Pune"),
    (r"vidarbha|jamtha", "VCA Stadium, Nagpur"),
    (r"aca-vdca|aca vdca|ys rajasekhara|visakhapatnam|vizag", "ACA-VDCA Stadium, Visakhapatnam"),
    (r"holkar", "Holkar Stadium, Indore"),
    (r"jsca|ranchi", "JSCA Stadium, Ranchi"),
    (r"barabati|cuttack", "Barabati Stadium, Cuttack"),
    (r"saurashtra|rajkot", "Saurashtra CA Stadium, Rajkot"),
    (r"green park|kanpur", "Green Park, Kanpur"),
    (r"raipur|shaheed veer narayan", "Shaheed Veer Narayan Singh Stadium, Raipur"),
    (r"dubai", "Dubai International Stadium"),
    (r"sharjah", "Sharjah Cricket Stadium"),
    (r"zayed|abu dhabi", "Zayed Cricket Stadium, Abu Dhabi"),
]


def canonical_venue(raw: str) -> str:
    low = str(raw).lower()
    for pattern, name in VENUE_RULES:
        if re.search(pattern, low):
            return name
    # Fallback: drop the city suffix and punctuation so variants still merge.
    return re.sub(r"\s+", " ", str(raw).split(",")[0].replace(".", " ")).strip()


# --------------------------------------------------------------------------
# Match info
# --------------------------------------------------------------------------
def _parse_info_file(path: Path) -> tuple[dict, list[dict], dict[str, str]]:
    """Return (match dict, players list, registry name->id) for one *_info.csv."""
    info: dict[str, object] = {"teams": [], "dates": []}
    players: list[dict] = []
    registry: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split(",")
            if len(parts) < 3 or parts[0] != "info":
                continue
            key = parts[1]
            if key == "team":
                info["teams"].append(parts[2])
            elif key == "date":
                info["dates"].append(parts[2])
            elif key == "player":
                players.append({"team_raw": parts[2], "player": ",".join(parts[3:])})
            elif key == "registry" and parts[2] == "people":
                registry[",".join(parts[3:-1])] = parts[-1]
            elif key == "target_overs":
                info["target_overs"] = float(parts[3])
            elif key == "target_runs":
                info["target_runs"] = int(parts[3])
            elif key not in info:  # keep the first value (e.g. first umpire)
                info[key] = ",".join(parts[2:])
    return info, players, registry


def load_matches() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Parse every *_info.csv into matches, match_players and people-id tables."""
    rows, player_rows, reg_rows = [], [], []
    for path in sorted(CSV2_DIR.glob("*_info.csv")):
        info, players, registry = _parse_info_file(path)
        match_id = int(path.name.split("_")[0])
        start = pd.to_datetime(info["dates"][0], format="%Y/%m/%d")
        teams = info["teams"]
        target_overs = info.get("target_overs", np.nan)
        rows.append(
            {
                "match_id": match_id,
                "season": start.year,  # Cricsheet labels like '2007/08' -> calendar year
                "season_label": info.get("season"),
                "date": start,
                "venue_raw": info.get("venue"),
                "venue": canonical_venue(info.get("venue", "")),
                "city": info.get("city"),
                "team1": team_code(teams[0]),
                "team2": team_code(teams[1]),
                "toss_winner": team_code(info.get("toss_winner")),
                "toss_decision": info.get("toss_decision"),
                "winner": team_code(info.get("winner")),
                "outcome": info.get("outcome"),  # 'tie' / 'no result' / None
                "method": info.get("method"),  # 'D/L' when rain rules applied
                "eliminator": team_code(info.get("eliminator")),  # super-over winner
                "target_overs": target_overs,
                "match_number": pd.to_numeric(info.get("match_number"), errors="coerce"),
                "player_of_match": info.get("player_of_match"),
            }
        )
        for p in players:
            player_rows.append(
                {"match_id": match_id, "team": team_code(p["team_raw"]), "player": p["player"],
                 "cricsheet_id": registry.get(p["player"])}
            )
        for name, pid in registry.items():
            reg_rows.append({"cricsheet_id": pid, "cricsheet_name": name})

    matches = pd.DataFrame(rows)
    # Playoff matches carry no league match number in Cricsheet.
    matches["is_playoff"] = matches["match_number"].isna()
    # A tied match decided by super over: the super-over winner is the result.
    matches["winner"] = matches["winner"].fillna(matches["eliminator"])
    # Rain-affected = D/L applied, or overs reduced below 20, or abandoned.
    matches["rain_affected"] = (
        matches["method"].notna()
        | (matches["target_overs"].fillna(20) < 20)
        | (matches["outcome"] == "no result")
    )
    match_players = pd.DataFrame(player_rows)
    people = pd.DataFrame(reg_rows).drop_duplicates()
    return matches, match_players, people


# --------------------------------------------------------------------------
# Ball by ball
# --------------------------------------------------------------------------
def load_balls() -> pd.DataFrame:
    """Read all csv2 delivery files into one clean ball-level table."""
    frames = []
    for path in sorted(CSV2_DIR.glob("*.csv")):
        # Only per-match files ('<match_id>.csv'); skips *_info.csv and the
        # combined all_matches.csv that ships in the same zip.
        if not path.stem.isdigit():
            continue
        # `ball` must be read as text: '0.10' (10th delivery of an over with
        # extras) would otherwise collapse to 0.1.
        frames.append(pd.read_csv(path, dtype={"ball": str}, low_memory=False))
    raw = pd.concat(frames, ignore_index=True)

    over_str = raw["ball"].str.split(".", n=1, expand=True)
    for col in ["wides", "noballs", "byes", "legbyes", "penalty"]:
        raw[col] = raw[col].fillna(0).astype(int)

    balls = pd.DataFrame(
        {
            "match_id": raw["match_id"].astype(int),
            "innings": raw["innings"].astype(int),
            "over": over_str[0].astype(int) + 1,  # 1-based over number
            "ball": over_str[1].astype(int),  # delivery number within over (incl. extras)
            "ball_label": raw["ball"],
            "batting_team": raw["batting_team"].map(team_code),
            "bowling_team": raw["bowling_team"].map(team_code),
            "batter": raw["striker"],
            "non_striker": raw["non_striker"],
            "bowler": raw["bowler"],
            "runs_batter": raw["runs_off_bat"].astype(int),
            "extras": raw["extras"].astype(int),
            "wides": raw["wides"],
            "noballs": raw["noballs"],
            "byes": raw["byes"],
            "legbyes": raw["legbyes"],
            "penalty": raw["penalty"],
            "wicket_kind": raw["wicket_type"],
            "player_dismissed": raw["player_dismissed"],
            "other_wicket_kind": raw["other_wicket_type"],
            "other_player_dismissed": raw["other_player_dismissed"],
            "fielder_1": raw.get("fielder_1"),
        }
    )
    balls["total_runs"] = balls["runs_batter"] + balls["extras"]
    balls["wicket"] = balls["player_dismissed"].notna() & ~balls["wicket_kind"].isin(NON_DISMISSALS)
    # Wides and no-balls do not count as one of the six legal balls.
    balls["legal_ball"] = (balls["wides"] == 0) & (balls["noballs"] == 0)
    # A wide is not a ball faced by the batter; a no-ball is.
    balls["ball_faced"] = balls["wides"] == 0
    # Runs charged to the bowler exclude byes, leg-byes and penalties.
    balls["bowler_runs"] = balls["runs_batter"] + balls["wides"] + balls["noballs"]
    balls["bowler_wicket"] = balls["wicket_kind"].isin(BOWLER_WICKETS)
    # Super overs are innings 3+ in Cricsheet; they are excluded everywhere.
    balls["super_over"] = balls["innings"] > 2
    return balls


def build_interim() -> dict[str, pd.DataFrame]:
    """Run the Cricsheet ingest and write the interim parquet files."""
    ensure_dirs()
    matches, match_players, people = load_matches()
    balls = load_balls()
    balls = balls.merge(matches[["match_id", "season", "date", "venue"]], on="match_id", how="left")
    matches.to_parquet(INTERIM_DIR / "matches.parquet", index=False)
    match_players.to_parquet(INTERIM_DIR / "match_players.parquet", index=False)
    people.to_parquet(INTERIM_DIR / "people.parquet", index=False)
    balls.to_parquet(INTERIM_DIR / "balls.parquet", index=False)
    return {"matches": matches, "match_players": match_players, "people": people, "balls": balls}


def read_interim(name: str) -> pd.DataFrame:
    return pd.read_parquet(INTERIM_DIR / f"{name}.parquet")


def load_auction() -> pd.DataFrame:
    """Auction + retention records (built by src/wiki_auction.py)."""
    return pd.read_csv(AUCTION_RAW_DIR / "auction_records.csv")


if __name__ == "__main__":
    out = build_interim()
    for k, v in out.items():
        print(k, v.shape)

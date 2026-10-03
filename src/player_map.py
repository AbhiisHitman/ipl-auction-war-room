"""Map auction names (Wikipedia, full names) to Cricsheet names (initials).

'Ruturaj Gaikwad' -> 'RD Gaikwad', 'Varun Chakaravarthy' -> 'CV Varun'.

Method (simple and explainable):
  1. Manual overrides CSV wins.
  2. Candidate Cricsheet players are scored on
       - surname match   (Cricsheet surname appears in the full name)   +50
       - initials match  (first initial agrees)            +20 / contradicts -25
       - spelled-out first name contradicts                                 -40
       - team context    same franchise that season +30; no IPL game within
                         2 seasons of the auction record -20
       - fuzzy similarity (rapidfuzz token_set_ratio x 0.2)              +0..20
  3. Greedy one-to-one assignment, highest score first, minimum score 70; a
     Cricsheet player can be claimed only once. Exact ties need an override.
Unmatched players are reported, never silently dropped.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz

from .config import AUCTION_RAW_DIR, PROCESSED_DIR

OVERRIDES = AUCTION_RAW_DIR / "player_map_overrides.csv"
ACCEPT_SCORE = 70


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace(".", " ").replace("-", " ").replace("'", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _tokens(s: str) -> list[str]:
    return _norm(s).split()


def score_pair(full_name: str, cs_name: str, same_team: bool, recent: bool = True) -> float:
    full_t, cs_t = _tokens(full_name), _tokens(cs_name)
    if not full_t or not cs_t:
        return 0.0
    if _norm(full_name) == _norm(cs_name):
        return 100.0 + (30 if same_team else 0)
    score = 0.0
    cs_last = cs_t[-1]
    if cs_last in full_t or any(fuzz.ratio(cs_last, t) >= 90 for t in full_t if len(t) > 3):
        score += 50
    # Cricsheet usually writes leading initials ('RD'); compare first letters.
    # Cricsheet writes initials in capitals ('RD Gaikwad', 'PHKD Mendis').
    raw_first = str(cs_name).split()[0] if len(cs_t) > 1 else ""
    first_is_initials = raw_first.isupper() and raw_first.isalpha()
    cs_initials = "".join(t[0] for t in cs_t[:-1]) if len(cs_t) > 1 else ""
    if first_is_initials:
        if full_t[0][0] == raw_first[0].lower():
            score += 20
        elif full_t[0][0] in raw_first.lower():
            score += 5  # e.g. 'CV Varun' for Varun Chakravarthy
        else:
            score -= 25  # initials contradict the first name ('RK' vs 'Pratham')
    elif len(cs_t) > 1:
        if full_t[0][0] in cs_initials:
            score += 20
        # A spelled-out first name must agree ('Harbhajan Singh' is not 'Pratham Singh').
        if not any(fuzz.ratio(cs_t[0], t) >= 85 for t in full_t):
            score -= 40
    # Team context: same franchise that season (or the season before) is strong
    # evidence; no IPL game within 2 seasons of the auction record is a red flag.
    score += 30 if same_team else (0 if recent else -20)
    score += 0.2 * fuzz.token_set_ratio(_norm(full_name), _norm(cs_name))
    return score


def build_player_map(auction: pd.DataFrame, match_players: pd.DataFrame,
                     matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (player_map, match_report)."""
    mp = match_players.merge(matches[["match_id", "season"]], on="match_id")
    # Team-season appearances per Cricsheet player.
    cs_team_seasons = mp.groupby(["player", "cricsheet_id"]).apply(
        lambda g: set(zip(g["team"], g["season"])), include_groups=False
    ).reset_index(name="team_seasons")
    cs_team_seasons = cs_team_seasons[cs_team_seasons["team_seasons"].map(
        lambda s: max(y for _, y in s) >= 2019)]  # only players active recently

    overrides = (pd.read_csv(OVERRIDES) if OVERRIDES.exists()
                 else pd.DataFrame(columns=["player_name", "cricsheet_name"]))
    override_map = dict(zip(overrides["player_name"], overrides["cricsheet_name"]))

    # Score every plausible (auction name, Cricsheet name) pair.
    cs_rows = list(cs_team_seasons.itertuples(index=False))
    pairs: list[tuple[float, str, str, str]] = []
    rows = []
    names = []
    for name, grp in auction.groupby("person"):
        contexts = set(zip(grp["team"], grp["season"]))
        keys = [name, *grp["player_name"].unique()]
        hit = next((k for k in keys if k in override_map), None)
        if hit is not None:
            name_key = hit
            cs = override_map[name_key]
            cid = cs_team_seasons.loc[cs_team_seasons["player"] == cs, "cricsheet_id"]
            rows.append({"person": name, "cricsheet_name": cs if pd.notna(cs) else None,
                         "cricsheet_id": cid.iloc[0] if len(cid) else None,
                         "score": None, "method": "manual"})
            continue
        names.append(name)
        # Score against every spelling of this person's name; keep the best.
        spellings = list(dict.fromkeys(grp["player_name"].tolist() + [re.sub(r" \(.*\)$", "", name)]))
        full_t = set(t for sp in spellings for t in _tokens(sp))
        for c in cs_rows:
            cs_t = _tokens(c.player)
            # Cheap pre-filter: share at least one token (or be fuzzy-similar).
            if not (full_t & set(cs_t)) and fuzz.token_set_ratio(_norm(name), _norm(c.player)) < 70:
                continue
            same_team = any((t, y) in c.team_seasons or (t, y - 1) in c.team_seasons
                            for t, y in contexts)
            recent = any(abs(y - y2) <= 2 for _, y in contexts for _, y2 in c.team_seasons)
            sc = max(score_pair(sp, c.player, same_team, recent) for sp in spellings)
            pairs.append((sc, name, c.player, c.cricsheet_id))

    # Greedy one-to-one assignment: highest-scoring pairs first, and a Cricsheet
    # player can only be claimed once (so 'Rinku Singh' takes 'RK Singh' and
    # 'Pratham Singh' cannot). Exact ties for the same name stay ambiguous.
    pairs.sort(key=lambda p: -p[0])
    taken_cs = {r["cricsheet_name"] for r in rows if r["cricsheet_name"]}
    assigned: dict[str, tuple] = {}
    best_seen: dict[str, tuple] = {}
    for sc, name, cs, cid in pairs:
        best_seen.setdefault(name, (sc, cs))
        if name in assigned or cs in taken_cs or sc < ACCEPT_SCORE:
            continue
        rival = [p for p in pairs if p[1] == name and p[2] != cs and p[2] not in taken_cs and p[0] == sc]
        if rival:
            continue  # genuine tie -> needs a manual override
        assigned[name] = (sc, cs, cid)
        taken_cs.add(cs)
    for name in names:
        if name in assigned:
            sc, cs, cid = assigned[name]
            rows.append({"person": name, "cricsheet_name": cs, "cricsheet_id": cid,
                         "score": round(sc, 1), "method": "auto"})
        else:
            sc, cs = best_seen.get(name, (0.0, None))
            rows.append({"person": name, "cricsheet_name": None, "cricsheet_id": None,
                         "score": round(sc, 1), "best_guess": cs,
                         "method": "ambiguous" if sc >= ACCEPT_SCORE else "unmatched"})
    pmap = pd.DataFrame(rows)

    # Report: match rate by season, split by whether the player had IPL history.
    rep = auction.merge(pmap[["person", "cricsheet_name"]], on="person", how="left")
    rep["matched"] = rep["cricsheet_name"].notna()
    # "Has IPL history" = Wikipedia lists IPL matches > 0 for any of the person's
    # rows, or we matched them; retained players without a count are assumed yes.
    hist = rep.groupby("person")["ipl_matches"].max()
    rep["has_ipl_history"] = (rep["person"].map(hist).fillna(1).gt(0)) | rep["matched"]
    report = rep.groupby("season").agg(
        players=("person", "nunique"),
        matched_pct=("matched", "mean"),
        with_history=("has_ipl_history", "sum"),
    )
    report["matched_pct_with_history"] = rep[rep["has_ipl_history"]].groupby("season")["matched"].mean()
    report = report.round(3)
    pmap.to_csv(PROCESSED_DIR / "player_map.csv", index=False)
    report.to_csv(PROCESSED_DIR / "player_map_report.csv")
    pmap[pmap["cricsheet_name"].isna()].to_csv(PROCESSED_DIR / "player_map_unmatched.csv", index=False)
    return pmap, report

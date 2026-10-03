"""Team-name normalisation (historical names -> current franchise code)."""
from __future__ import annotations

from functools import lru_cache

from .config import teams_config


@lru_cache(maxsize=1)
def _alias_map() -> dict[str, str]:
    cfg = teams_config()
    out: dict[str, str] = {}
    for code, t in cfg["teams"].items():
        for a in t["aliases"]:
            out[a.lower()] = code
    for code, aliases in cfg["defunct"].items():
        for a in aliases:
            out[a.lower()] = code
    return out


def team_code(name: str | None) -> str | None:
    """Map any team name used in the raw data to a franchise code, e.g.
    'Kings XI Punjab' -> 'PBKS'. Returns None for blanks, raises on unknowns so
    a new spelling is noticed instead of silently dropped."""
    if name is None or str(name).strip() == "" or str(name).lower() == "nan":
        return None
    key = str(name).strip().lower()
    m = _alias_map()
    if key not in m:
        raise KeyError(f"Unknown team name: {name!r} - add it to config/teams.yaml")
    return m[key]


def active_codes() -> list[str]:
    return list(teams_config()["teams"].keys())


def full_name(code: str) -> str:
    return teams_config()["teams"][code]["name"]

"""Shared paths and config loaders.

Every module imports paths from here so notebooks, the Excel builders and the
app all read and write the same files.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CRICSHEET_DIR = RAW_DIR / "cricsheet"
AUCTION_RAW_DIR = RAW_DIR / "auction"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = ROOT / "outputs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
EXCEL_DIR = OUTPUTS_DIR / "excel"
DOCS_DIR = ROOT / "docs"


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    """Load `config/<name>.yaml` (cached; configs are read-only at runtime)."""
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def rules() -> dict[str, Any]:
    return load_yaml("rules")


def assumptions() -> dict[str, Any]:
    return load_yaml("assumptions")


def valuation_params() -> dict[str, Any]:
    return load_yaml("valuation")


def teams_config() -> dict[str, Any]:
    return load_yaml("teams")


def ensure_dirs() -> None:
    for d in (INTERIM_DIR, PROCESSED_DIR, CHARTS_DIR, EXCEL_DIR, OUTPUTS_DIR / "deck"):
        d.mkdir(parents=True, exist_ok=True)

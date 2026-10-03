"""Player master table: one row per player who matters for the next auction.

Joins Cricsheet performance (Impact Score, roles) with contract data
(auction/retention records), Wikipedia bios (age, bowling style, caps) and
the current (2026) squads.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CURRENT_SEASON = 2026  # latest completed season / current contracts


def latest_contracts(auction: pd.DataFrame) -> pd.DataFrame:
    """Latest auction/retention record per person (contract team & salary)."""
    a = auction.sort_values(["season", "status"])  # 'sold' after 'retained' in the same season
    last = a.groupby("person").tail(1).set_index("person")
    first_seen = a.groupby("person")["season"].min().rename("first_contract_season")
    out = last[["display_name", "season", "team", "sold_price_lakh", "status",
                "nationality", "overseas", "role", "base_price_lakh"]].rename(columns={
        "season": "contract_season", "team": "contract_team", "sold_price_lakh": "salary_lakh",
        "status": "contract_status", "role": "auction_role", "base_price_lakh": "last_base_price_lakh"})
    # Most recent *auction* (not retention) price is the cleanest market signal.
    sold = a[a["status"] == "sold"].groupby("person").tail(1).set_index("person")
    out["last_auction_season"] = sold["season"]
    out["last_auction_price_lakh"] = sold["sold_price_lakh"]
    # Capped flag from the latest auction record that states it.
    capped = a.dropna(subset=["capped"]).groupby("person")["capped"].last()
    out["capped_auction"] = capped
    return out.join(first_seen)


def build_players(auction: pd.DataFrame, pmap: pd.DataFrame, bios: pd.DataFrame,
                  impact: pd.DataFrame, roles: pd.DataFrame, avail: pd.Series,
                  auction_date: pd.Timestamp) -> pd.DataFrame:
    """Master table keyed by Cricsheet name (`player`), with `person` link."""
    contracts = latest_contracts(auction)
    link = pmap.dropna(subset=["cricsheet_name"])[["person", "cricsheet_name"]]

    # Start from everyone with an impact score, then add contracted players
    # without one (debutants / no recent IPL games).
    base = impact.merge(link, left_on="player", right_on="cricsheet_name", how="left").drop(columns="cricsheet_name")
    no_data = contracts.index.difference(base["person"].dropna())
    extra = pd.DataFrame({"person": no_data})
    extra["player"] = extra["person"].map(link.set_index("person")["cricsheet_name"])
    extra["player"] = extra["player"].fillna(extra["person"])
    base = pd.concat([base, extra], ignore_index=True)

    base = base.merge(contracts, left_on="person", right_index=True, how="left")
    base = base.merge(bios[["person", "birth_date", "bowling_type", "bowling_style",
                            "wiki_role", "capped_intl"]], on="person", how="left")
    base = base.merge(roles, on="player", how="left")
    base["roles"] = base["roles"].apply(lambda r: r if isinstance(r, list) else [])
    base["availability"] = base["player"].map(avail)

    base["display_name"] = base["display_name"].fillna(base["player"])
    base["has_impact"] = base["impact"].notna()
    bd = pd.to_datetime(base["birth_date"], errors="coerce")
    base["age_at_auction"] = ((auction_date - bd).dt.days / 365.25).round(1)

    # Capped: an international cap (Wikipedia) or a 'capped' auction listing -
    # once capped, a player stays capped (old auction rows can be stale).
    # IPL rule: Indians with no international game in 5 years count as uncapped
    # (e.g. MS Dhoni retained at the uncapped Rs 4 cr rate in 2025).
    cap = (base["capped_intl"].fillna(False).astype(bool)
           | base["capped_auction"].fillna(False).astype(bool))
    unknown = base["capped_intl"].isna() & base["capped_auction"].isna()
    cap = cap.astype("object").where(~unknown, None)
    uncapped_rate = (auction["status"].eq("retained") & auction["season"].eq(2025)
                     & auction["sold_price_lakh"].eq(400) & auction["nationality"].eq("IND"))
    dhoni_rule = set(auction.loc[uncapped_rate, "person"])
    cap = np.where(base["person"].isin(dhoni_rule), False, cap)
    base["capped"] = pd.Series(cap, index=base.index).astype("boolean")
    base["overseas"] = base["overseas"].astype("boolean")

    base["is_keeper_listed"] = (base["wiki_role"].fillna("").str.contains("keeper", case=False)
                                | base["auction_role"].fillna("").eq("Wicket-keeper"))
    # Current squad = contracted for the current season.
    base["current_team"] = np.where(base["contract_season"].eq(CURRENT_SEASON), base["contract_team"], None)
    base["current_salary_lakh"] = np.where(base["contract_season"].eq(CURRENT_SEASON), base["salary_lakh"], np.nan)
    return base

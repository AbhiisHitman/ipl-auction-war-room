"""Auction market model: what does the market pay for impact?

log(price) = a + b * impact + c * overseas + d * capped + season effect

* Fair value   = typical (median) price the market pays for this profile = exp(predicted log price)
* Mispricing % = (fair value - actual price) / actual price
                 (positive = the buyer got a bargain / player was underpriced)
* Bid ceiling  = fair value x (1 + strategic premium for gap-filling roles)
* Expected price (Model B) adds the previous contract as a reputation proxy:
  the market pays for name as well as output, so this is what a player will
  likely cost. Optimiser cost = expected price x (1 + rival inflation).

Training data: every player SOLD at the 2022-2026 auctions who had enough
IPL data in the 3 seasons before that auction to get an Impact Score.
Retentions are excluded (they are negotiated, not bid for).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .config import rules


@dataclass
class MarketModel:
    fit: object  # statsmodels results
    smearing: float
    train: pd.DataFrame

    def predict_lakh(self, df: pd.DataFrame) -> pd.Series:
        """Typical (median) price for this profile: exp(predicted log price).
        We deliberately do NOT apply the smearing factor: auction prices are
        very right-skewed (a few bidding wars), so the mean price would make
        almost every player look 'underpriced'."""
        return np.exp(self.fit.predict(df))

    def summary_table(self) -> pd.DataFrame:
        res = self.fit
        return pd.DataFrame({"coef": res.params, "std_err": res.bse, "p_value": res.pvalues}).round(4)


def previous_salary(auction: pd.DataFrame, person: str, season: int) -> float:
    prev = auction[(auction["person"] == person) & (auction["season"] < season)]
    return float(prev.sort_values("season")["sold_price_lakh"].iloc[-1]) if len(prev) else np.nan


def training_set(auction: pd.DataFrame, pmap: pd.DataFrame,
                 impact_by_season: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Sold records joined with the buyer's information at auction time."""
    sold = auction[auction["status"] == "sold"].copy()
    # Reputation proxy: the player's most recent contract before this auction.
    sold["prev_salary_lakh"] = [previous_salary(auction, p, s) for p, s in zip(sold["person"], sold["season"])]
    sold = sold.merge(pmap[["person", "cricsheet_name"]], on="person", how="left")
    frames = []
    for season, imp in impact_by_season.items():
        s = sold[sold["season"] == season].merge(
            imp[["player", "impact", "bat_impact", "bowl_impact", "impact_Powerplay",
                 "impact_Middle", "impact_Death", "balls_faced_3y", "balls_bowled_3y"]],
            left_on="cricsheet_name", right_on="player", how="inner")
        frames.append(s)
    t = pd.concat(frames, ignore_index=True)
    t["log_price"] = np.log(t["sold_price_lakh"])
    t["overseas"] = t["overseas"].astype(int)
    t["capped"] = t["capped"].fillna(True).astype(int)
    t["season_cat"] = t["season"].astype(str)
    add_prev_features(t)
    return t


def add_prev_features(df: pd.DataFrame) -> None:
    df["has_prev"] = df["prev_salary_lakh"].notna().astype(int)
    df["log_prev"] = np.log(df["prev_salary_lakh"].where(df["prev_salary_lakh"] > 0)).fillna(0.0)


FAIR_VALUE_FORMULA = "log_price ~ impact + overseas + capped + C(season_cat)"
PRICE_FORMULA = "log_price ~ impact + overseas + capped + has_prev + log_prev + C(season_cat)"


def fit_market_model(train: pd.DataFrame, formula: str = FAIR_VALUE_FORMULA) -> MarketModel:
    """Model A (default): performance-only fair value.
    Model B (PRICE_FORMULA): adds the previous contract as a reputation proxy,
    used to predict what a player will actually cost."""
    fit = smf.ols(formula, data=train).fit()
    smearing = float(np.mean(np.exp(fit.resid)))  # Duan's factor, reported only
    train = train.copy()
    train["fair_value_lakh"] = np.exp(fit.fittedvalues)
    train["mispricing_pct"] = (train["fair_value_lakh"] - train["sold_price_lakh"]) / train["sold_price_lakh"]
    return MarketModel(fit=fit, smearing=smearing, train=train)


def phase_specialism(df: pd.DataFrame) -> pd.Series:
    """The phase where a player adds the most impact per match."""
    cols = ["impact_Powerplay", "impact_Middle", "impact_Death"]
    return df[cols].idxmax(axis=1).str.replace("impact_", "", regex=False)


def mispricing_by_group(train: pd.DataFrame, group: str) -> pd.DataFrame:
    """Median mispricing per group. Median, not mean: one bidding war should not
    swing the conclusion."""
    g = train.groupby(group).agg(
        players=("player", "size"),
        median_mispricing_pct=("mispricing_pct", "median"),
        mean_price_cr=("sold_price_lakh", lambda x: x.mean() / 100),
        mean_impact=("impact", "mean"),
    )
    return g.sort_values("median_mispricing_pct", ascending=False).round(3)


def _auction_frame(players: pd.DataFrame, mode: str) -> pd.DataFrame:
    ref_season = "2026" if mode == "mini_2027" else "2025"
    X = pd.DataFrame({
        "impact": players["impact"],
        "overseas": players["overseas"].fillna(False).astype(int),
        "capped": players["capped"].fillna(True).astype(int),
        "season_cat": ref_season,
        # Previous contract = current / latest salary.
        "prev_salary_lakh": players["salary_lakh"],
    }, index=players.index)
    add_prev_features(X)
    return X


def _bound(fv: pd.Series, players: pd.DataFrame, mode: str) -> pd.Series:
    r = rules()
    if mode == "mega_2028":
        fv = fv * r["modes"][mode]["purse_lakh"]["value"] / 12000  # 2025 mega purse was Rs 120 cr
    fv = fv.clip(lower=r["common"]["min_base_price_lakh"]["value"])
    cap = r["common"]["overseas_max_fee_lakh"]["value"]
    fv = np.where(players["overseas"].fillna(False).astype(bool), np.minimum(fv, cap), fv)
    return pd.Series(fv, index=players.index).round(0)


def expected_prices_for_auction(price_model: MarketModel, players: pd.DataFrame, mode: str) -> pd.Series:
    """Likely clearing price (lakh) from Model B (performance + reputation)."""
    return _bound(price_model.predict_lakh(_auction_frame(players, mode)), players, mode)


def fair_values_for_auction(model: MarketModel, players: pd.DataFrame, mode: str) -> pd.Series:
    """Predicted price (lakh) for the target auction.

    mini_2027: uses the latest mini-auction (2026) market level.
    mega_2028: uses the latest mega-auction (2025) market level, scaled by the
               ratio of purses (assumption, see docs/methodology.md)."""
    r = rules()
    mode_cfg = r["modes"][mode]
    ref_season = "2026" if mode == "mini_2027" else "2025"
    X = pd.DataFrame({
        "impact": players["impact"],
        "overseas": players["overseas"].fillna(False).astype(int),
        "capped": players["capped"].fillna(True).astype(int),
        "season_cat": ref_season,
    }, index=players.index)
    fv = model.predict_lakh(X)
    if mode == "mega_2028":
        fv = fv * mode_cfg["purse_lakh"]["value"] / 12000  # 2025 mega purse was Rs 120 cr
    floor = r["common"]["min_base_price_lakh"]["value"]
    fv = fv.clip(lower=floor)
    # Overseas players cannot be paid above the cap.
    cap = r["common"]["overseas_max_fee_lakh"]["value"]
    fv = np.where(players["overseas"].fillna(False).astype(bool), np.minimum(fv, cap), fv)
    return pd.Series(fv, index=players.index).round(0)


def _price_vs_fair(m: float) -> str:
    """Turn a median mispricing into plain words (price relative to fair value)."""
    ratio = 1 / (1 + m)  # actual price / fair value
    if ratio < 1:
        return f"sell for {1 - ratio:.0%} below fair value"
    return f"sell for {ratio:.1f}x fair value"


def top_insights(train: pd.DataFrame, model: MarketModel) -> list[str]:
    """Three headline market insights, each with a number."""
    by_role = mispricing_by_group(train.dropna(subset=["primary_role"]), "primary_role")
    by_phase = mispricing_by_group(train, "phase_specialism")
    res = model.fit
    b = res.params.get("impact", np.nan)
    cap = res.params.get("capped", np.nan)
    ins = []
    big = by_role[by_role["players"] >= 8]
    if len(big) >= 2:
        lo, hi = big.head(1), big.tail(1)
        ins.append(
            f"{lo.index[0]}s are the market's best value: they {_price_vs_fair(lo['median_mispricing_pct'].iloc[0])} "
            f"(median, n={int(lo['players'].iloc[0])}), while {hi.index[0].lower()}s "
            f"{_price_vs_fair(hi['median_mispricing_pct'].iloc[0])} (n={int(hi['players'].iloc[0])}).")
    if len(by_phase):
        best, worst = by_phase.head(1), by_phase.tail(1)
        ins.append(
            f"{best.index[0]} specialists {_price_vs_fair(best['median_mispricing_pct'].iloc[0])}, "
            f"vs {worst.index[0].lower()} specialists who {_price_vs_fair(worst['median_mispricing_pct'].iloc[0])} "
            f"(n={int(best['players'].iloc[0])} / {int(worst['players'].iloc[0])}).")
    ins.append(
        f"Output is only part of the price: +1 run/match of impact adds {np.expm1(b):.0%} to price, "
        f"but an international cap adds {np.expm1(cap):.0%}; impact and profile explain just "
        f"{res.rsquared:.0%} of price variation.")
    return ins

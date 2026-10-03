# Methodology

Every method in plain English: **what it does, why this choice, and its main limitation.**
Numbers quoted are from the current build (data to 31 May 2026; checked 3 Oct 2026).

---

## 1. Data pipeline (Phase 1)

| Step | What it does | Why | Main limitation |
|---|---|---|---|
| Ball-by-ball ingest (`src/ingest.py`) | Reads Cricsheet csv2 files into one table: 1,243 matches, 295,732 deliveries, 2008-2026. | Cricsheet is the open, complete, ball-level source. | No fielding, no ball-tracking (line/length/pace). |
| Season | Calendar year of the match (Cricsheet labels like `2007/08` map to 2008). | One season = one IPL edition. | - |
| Super overs | Excluded everywhere (innings 3+). | Not normal play; would distort phase rates. | - |
| Rain-affected matches | Flagged (D/L, overs < 20, no result) and left out of league baselines. | Shortened games change scoring tempo. | Player stats from those games are still counted. |
| Venues | Spelling variants and renamed grounds merged (e.g. Feroz Shah Kotla = Arun Jaitley Stadium). | Venue profiles need one name per ground. | - |
| Auction data (`src/wiki_auction.py`) | Parses the Wikipedia "List of <year> IPL personnel changes" tables: 2022-2026 sold + retained players with prices. | No free official dataset; Wikipedia tables cite ESPNcricinfo / IPLT20 and are complete for sold players. | **Unsold players are not listed**, so the market model only sees players who sold. 2025 tables list 180 sold vs 182 in the summary. |
| Player bios (`src/enrich.py`) | Reads each player's Wikipedia infobox: birth date, bowling style, role, international caps. | Gives age (for the Long-Term scenario) and pace / wrist-spin / finger-spin. | 6% of players have no article (mostly uncapped youngsters). |
| Name matching (`src/player_map.py`) | Links "Ruturaj Gaikwad" (Wikipedia) to "RD Gaikwad" (Cricsheet). Score = surname match +50, initials +20 / contradiction -25, spelled-out first-name contradiction -40, same team that season +30 (no IPL game within 2 years -20), fuzzy similarity up to +20. Greedy one-to-one assignment; 15 manual overrides (`data/raw/auction/player_map_overrides.csv`). | Simple, auditable rules; team context resolves common surnames (Singh, Sharma, Yadav). | Match rate for players with IPL history: 2022 89.8%, 2023 98.3%, 2024 95.0%, 2025 94.2%, 2026 90.0%. Unmatched players are listed in `data/processed/player_map_unmatched.csv`, never dropped silently. |

**Acceptance check:** match counts per season equal the Cricsheet file counts; zero duplicate deliveries (match, innings, ball); tests pass.

---

## 2. Franchise economics (Phase 2)

**What it does.** A per-team, per-season P&L (`src/economics.py`, mirrored by live formulas in `outputs/excel/franchise_model.xlsx`).

- **Revenue** = central media-rights share + central sponsorship share + team sponsorship + ticketing + merchandise + prize money.
  - Central media = Rs 48,390 cr / 5 seasons x 50% franchise share / 10 teams = **Rs 484 cr per team**.
  - Ticketing = 7 home games x min(capacity, 60k) x 90% occupancy x 90% paid x Rs 2,500.
  - Sponsorship and merchandise scale with each team's Houlihan Lokey brand value.
- **Costs** = salaries + match fees (Rs 7.5 lakh x 12 players x matches) + staff, operations, marketing, travel, match-day costs, and an assumed 20% BCCI fee on team-generated revenue. The LSG/GT franchise-fee instalments are shown **below** operating profit because they rest on an assumption (10 equal annual payments).
- **Scenarios**: missed playoffs / made playoffs / won title, which differ in prize money, playoff match fees and sponsorship/merchandise uplift.

**Why.** The engagement question includes "maximise commercial value", so the squad plan has to connect to money. Excel with live formulas lets a client change any input.

**Key insight.** About **76% of revenue is fixed central income**. For CSK, winning the title vs missing the playoffs changes revenue by only about **Rs 40 cr (~6%)**. Performance moves the thin team-generated slice on top, so the auction is about wins and brand, and overspending to win is hard to justify on money alone.

**Limitation.** Franchise financials are mostly assumptions (see `config/assumptions.yaml`; every item is marked `verified` or `assumption`). Revenue is calibrated to Houlihan Lokey's "top franchises earn ~Rs 650-700 cr", not to audited accounts.

**Acceptance check:** the Excel `Check` sheet compares Python and Excel for every team and scenario. The max difference is Rs 0.00004 cr, which is rounding.

---

## 3. Player valuation: the Impact Score (Phase 3)

**One sentence:** *the runs a player adds per match compared with a league-average player in the same phase and season.*

1. **Phase baseline**: league runs per ball for each season and phase (Powerplay 1-6, Middle 7-15, Death 16-20). Batters are measured per ball faced (wides excluded); bowlers per legal ball, charged with bat runs + wides + no-balls (not byes or leg-byes).
2. **Wicket value**: how many runs a wicket costs the batting side, from a run-expectancy table (2023-26 first innings, the Impact Player era). For every wicket that fell with *b* balls bowled and *w* wickets down, cost = average runs still to come from (b, w) minus from (b, w+1).

   | Phase | Wicket costs |
   |---|---|
   | Powerplay | **12.6 runs** |
   | Middle | **5.8 runs** |
   | Death | **1.8 runs** |

   Wickets matter most early, when there are many balls left to waste.
3. **Batting impact** = sum(runs - baseline) - (dismissals - expected dismissals) x wicket value.
   **Bowling impact** = sum(baseline - runs conceded) + (wickets - expected wickets) x wicket value.
   "Expected" uses the league's dismissal rate, so **an average player scores exactly 0** (tested).
4. **Per match**: season total / matches played.
5. **Small-sample shrinkage**: adjusted = raw x n / (n + 120), with n = balls faced (or bowled). After 120 balls we trust half the raw rate.
6. **Recency weighting**: last 3 seasons at 0.5 / 0.3 / 0.2 (Win-Now scenario 0.7 / 0.2 / 0.1), re-normalised over the seasons actually played.
7. Also reported: consistency (season-to-season SD), phase breakdown, availability (share of team games played in 3 years), age.

**Why.** It is a single number in runs, so a consultant can explain and compare batters and bowlers on one scale. Phase baselines stop death-over hitters and powerplay bowlers being judged against the wrong standard.

**Sanity check.** The top 20 going into 2027 are Sooryavanshi, Narine, Bhuvneshwar, Inglis, Bumrah, Holder, Kohli, Abhishek Sharma, Sai Sudharsan, Mohsin Khan, Klaasen, Gill, Hosein, Hazlewood, Archer, Marsh, KL Rahul, Patidar and Ngidi (`outputs/charts/top20_impact.png`). That is a mix of batters and bowlers a fan would recognise.

**Validation.** A team's *same-season* total impact explains **53% of the variation in win %** across 132 team-seasons (2012-2026). The metric captures what wins matches.

**Limitations.** Ignores fielding, captaincy and match situation beyond phase. It doesn't adjust for opposition or venue. Shrinkage pulls new players toward average, so breakout seasons are under-rated at first.

---

## 4. Market inefficiency (Phase 4)

**Model A, fair value (performance only):** `log(price) = a + b·impact + c·overseas + d·capped + season effect`, fitted on 284 players sold at the 2022-26 auctions who had an Impact Score at auction time.
- **Fair value** = exp(prediction): the *typical* (median) price for that profile. We do not apply a smearing correction: prices are very right-skewed, and the mean would make almost everyone look underpriced.
- **Mispricing %** = (fair value - price) / price. Positive means the buyer got a bargain.

**Model B, expected price (performance + reputation):** adds the player's previous contract (log salary) as a reputation proxy. R² rises from 0.30 to **0.38**, and the previous salary is highly significant (elasticity 0.34). The optimiser uses this to estimate what a player will *actually cost*.

**Bid ceiling** = fair value x (1 + strategic premium): +15% if the player fills a Red gap, +5% for Amber. When the expected price is above our ceiling, the recommendation says to bid only up to the ceiling or take the backup.

**Top-3 market insights** (from `data/processed/market_model.json`):
1. **Wrist spinners are the market's best value**: they sell for ~17% below fair value (n=17). **Anchors sell for 2.5x fair value** (n=24).
2. **Powerplay specialists sell ~18% below fair value; death specialists sell for 1.3x** (n=96 / 102). Teams pay up for the death overs.
3. **Output is only part of the price**: +1 run/match of impact adds 24% to price, but an international cap adds 157%. Impact and profile explain just 30% of price variation.

**Limitations.** Auction prices reflect bidding dynamics (purse left, rival needs, set order), not just value. Unsold players are missing (selection bias). Sample sizes are small for some roles (wicketkeepers n=4, all-rounders n=5). Missing variables include international form, age and marketability.

---

## 5. Squad gap analysis (Phase 5)

**Roles from data** (`src/squad.py`, 2024-26 window):

| Role | Rule |
|---|---|
| Opener | median batting position ≤ 2 |
| Anchor | median position 3-4 |
| Finisher | median position ≥ 5 and ≥ 35% of balls faced at the death |
| Middle-order | median position ≥ 5 otherwise |
| Wicketkeeper | ≥ 2 stumpings, or listed as a keeper |
| Death pacer | pace bowler with ≥ 30% of balls at the death |
| Powerplay pacer | other pace bowlers |
| Wrist / finger spinner | from the Wikipedia bowling style |
| All-rounder | ≥ 6 balls faced and ≥ 12 bowled per match |

Batting roles need ≥ 120 balls faced and bowling roles ≥ 120 balls bowled. Manual overrides go in `data/raw/role_overrides.csv`.

**Coverage matrix.** For a role needing *k* players, take the squad's k-th best player in that role and his league rank. **Green** if within the league's top 10k (starter quality for 10 teams), **Amber** within the top 15k, **Red** otherwise or if the squad has fewer than k players. Each Red role has a one-line explanation in `data/processed/coverage.csv`.

**Team-specific priorities** (`src/team_strategy.py`). Each franchise gets its own role weights from:
1. **Gaps**: Red x1.6, Amber x1.25.
2. **Home ground** (data-derived from 2026 fixtures): the spin-vs-pace economy ratio and the death-over run rate relative to the league adjust spin, pace and death roles (damped, bounded 0.85-1.20). Example: Hyderabad favours pace (spin 1.13x as expensive); Eden Gardens favours spin (1.13x).
3. **Situation**: 2026 finish and squad age set the stance (**Win Now** if the team made the playoffs; **Long-Term Build** if it missed and has an ageing core or finished 8th or lower).

**Limitation.** Thresholds are judgement calls (documented and configurable). All-rounder is strict by design (only about 9 players league-wide), so the minimum is 1 per team.

---

## 6. Squad optimiser (Phase 6)

**PuLP / CBC integer program** (`src/optimiser.py`):
- **Objective**: maximise sum(value x starter) + 0.1 x sum(value x in squad) - λ x total cost.
  - value = (impact - replacement level) x team role weight. Replacement level = 25th-percentile impact, i.e. a freely available player.
  - The 12 who play (XI + Impact Player) carry the value; depth counts 10%.
  - λ = opportunity cost of money: 10% of the pool's value per crore. Salary is a P&L cost, so the model won't keep an expensive bench player just because the purse isn't binding.
- **Constraints** (from `config/rules.yaml`): cost ≤ purse and ≥ 75% of purse; squad size 18-25; ≤ 8 overseas; ≤ 4 overseas among the 12 starters; role minimums (soft, heavily penalised); locked and excluded players.
- **Mini-auction (2027)**: keep each current player at his salary or release him; buy from the pool (unsigned players + players rivals are *projected* to release: salary ≥ 1.5x fair value and outside their top 12).
- **Mega-auction (2028)**: up to 6 retentions (≤ 5 capped, ≤ 2 uncapped) at the 2025 slab costs (cumulative Rs 18/32/43/61/75 cr; uncapped Rs 4 cr). Everyone else must be (re)bought. Rivals are assumed to retain their top 4.
- **Expected cost** = expected price (Model B) x (1 + rival inflation), floored at the Rs 30 lakh base price and capped at Rs 18 cr for overseas players.
- **Scenarios**: Win Now vs Long-Term (age curve: -5% per year over 31, +3% per year under 25), each at +10% / +20% / +30% rival inflation (`data/processed/scenarios.csv`).

**Excel Solver version.** `outputs/excel/squad_optimiser_<TEAM>.xlsx` contains the same problem in reduced form (own squad + top-60 pool candidates, no starter split). The Python solution is pre-loaded. Recalculating the workbook reproduces the PuLP objective (CSK 49.326 vs 49.325), and running Solver should return the same squad.

**Tests.** `tests/test_optimiser_and_economics.py` re-checks every hard constraint on solutions for 5 teams x 2 modes, retention limits, locks and exclusions, and that higher prices never raise squad strength.

**Limitations.** One team is optimised at a time: rivals don't react, and in the mega mode several teams' plans would chase the same players. Expected prices are model estimates, not bidding simulations. RTM cards aren't modelled explicitly.

---

## 7. Recommendations and impact estimate (Phase 7)

**Table** (`data/processed/recommendations.csv`, one row per player x team x mode): action (Buy / Buy back / Retain / Release), role, impact, fair value, expected cost, bid ceiling, a rationale that cites a number, a risk line (age ≥ 33, availability < 60%, volatility, small sample, projected-release dependency, overseas clashes), and a **backup** in the same role that costs no more than the target's bid ceiling.

**Impact chain**: squad strength → wins → playoffs → revenue (`src/impact_model.py`).
1. **Structural link**: win % = 0.505 + 0.0069 x realised team impact (runs/match). R² = 0.53, so +10 runs/match ≈ +7 points of win %.
2. **Realisation link**: realised = -2.96 + 0.445 x planned strength. R² = 0.04: only about 45% of a planned gain shows up the next season, because form, injuries and T20 randomness dominate.
3. Expected win % → playoff chance with a binomial over 14 games (the 4th-placed team needed a median of 8 wins in 2022-26; half credit at 7 for net-run-rate tie-breaks).
4. Playoff chance → probability-weighted P&L (P(title | playoffs) = 25%).

**Honest takeaway.** A well-run auction lifts playoff odds by a few points (mini) to around 10 points (mega). Revenue gains are modest because central income dominates. The case for disciplined, value-based bidding rests on cost control and win probability, not on a big revenue jump.

---

## Known limitations (summary)

- Auction prices reflect bidding dynamics, not only player value; unsold players are not in the data.
- The Impact Score ignores fielding, captaincy and match situation beyond phase.
- Small samples for new or uncapped players (shrinkage helps but under-rates breakouts).
- Franchise financials are largely assumption-based.
- Past performance predicts next season weakly (realisation R² 0.04): treat squad-strength gains as directional.
- 2027 purse and all 2028 mega-auction rules are assumptions until the BCCI announces them (`config/rules.yaml`).

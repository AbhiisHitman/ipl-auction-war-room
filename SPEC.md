# IPL Franchise Strategy — "Auction War Room"
## Complete Build Specification

> **How this spec was used:** the project was built one phase at a time, with a review after each phase against the acceptance criteria below.

---

## 0. Working principles

This is a portfolio project by a B.Tech CSE student applying to consulting firms (Bain, PwC, Deloitte, EY, Qwixpert). The project must read as a **consulting engagement**, not a coding exercise. Principles:

1. **Build one phase at a time** (Section 6). At the end of each phase, summarise what was built and check every acceptance criterion before moving on.
2. **Never fabricate data.** If a number (auction price, rule, revenue figure) is not in the data, look it up and cite the source in `docs/sources.md`, or mark it clearly as an **assumption** in `config/assumptions.yaml` with a reason.
3. **Verify current IPL rules** (purse size, squad min/max, overseas cap, retention/RTM rules, Impact Player rule) for the target auction before using them. Store them in `config/rules.yaml` with source links and the date checked; anything unverifiable is flagged as an assumption.
4. **Explain as you go.** Every method must be defensible in an interview. For every metric, model, or formula, add a plain-English explanation in `docs/methodology.md` (what it does, why this choice, its main limitation).
5. Keep all analysis logic in plain Python modules under `src/`, so the notebooks, Excel checks, and the app all use the same code.
6. Keep methods **simple and explainable** over complex. A consultant must be able to explain any metric in one sentence.
7. Write clean, commented code with type hints. Add basic tests with `pytest` for the core calculations.

---

## 1. Project Summary

**Client (hypothetical):** [FRANCHISE NAME] — an IPL franchise.

**Key question:** *"How should [FRANCHISE NAME] rebuild its squad and allocate its purse for the [TARGET AUCTION, e.g. IPL 2027 auction] to maximise wins and commercial value?"*

**Issue tree (the structure of the entire project):**
1. How does the franchise make and spend money? → *Franchise economics model*
2. What actually wins IPL matches? → *Player valuation metric*
3. Where does the auction market misprice players? → *Market inefficiency analysis*
4. Where is our squad weak? → *Squad gap analysis*
5. What is the best squad we can afford? → *Squad optimiser + scenarios*
6. What exactly should we do? → *Player recommendations (Buy / Retain / Release with bid ceilings)*
7. What is it worth? → *Impact estimate linking performance to revenue*

**Final deliverables:**
- Clean data pipeline + analysis modules (Python)
- Franchise P&L model with live formulas (Excel)
- Squad optimiser in Python (PuLP) **and** a matching Excel Solver version
- Interactive web app ("Auction War Room") built in Streamlit, deployed
- Draft consulting deck (python-pptx), 12–15 slides
- Executive-summary-style README

---

## 2. Placeholders to Fill Before Starting

| Placeholder | Value |
|---|---|
| `[FRANCHISE NAME]` | e.g. a team that finished bottom half last season |
| `[TARGET AUCTION]` | e.g. next IPL auction |
| `[SEASONS IN SCOPE]` | e.g. 2019–2026 (valuation uses the last 3 seasons most heavily) |
| `[RETAINED PLAYERS]` | Current squad list for the franchise (compiled from verified sources) |
| `[GITHUB REPO NAME]` | e.g. `ipl-auction-war-room` |

---

## 3. Tech Stack

- **Python 3.11+**: pandas, numpy, pulp, statsmodels (or scikit-learn), plotly, pyyaml, openpyxl, python-pptx, pytest
- **App**: Streamlit (multipage), deployed on Streamlit Community Cloud
- **Excel**: `.xlsx` generated with openpyxl, using **real Excel formulas** (not hard-coded values) so the model stays live
- Optional later: FastAPI + React version of the app (only after everything else is done)

---

## 4. Repository Structure

```
ipl-auction-war-room/
├── README.md                  # Executive summary style
├── SPEC.md                    # This file
├── requirements.txt
├── config/
│   ├── rules.yaml             # Verified IPL rules + sources + date checked
│   ├── assumptions.yaml       # Every assumption, with reason
│   └── valuation.yaml         # Tunable metric parameters
├── data/
│   ├── raw/
│   │   ├── cricsheet/         # Cricsheet IPL ball-by-ball files
│   │   └── auction/           # Auction price CSVs (manual download)
│   ├── interim/
│   └── processed/             # Clean tables used by app + analysis
├── src/
│   ├── ingest.py              # Load + clean Cricsheet + auction data
│   ├── features.py            # Phase splits, player-season tables
│   ├── valuation.py           # Impact score
│   ├── market.py              # Fair value, mispricing, bid ceilings
│   ├── squad.py               # Role classification + gap matrix
│   ├── optimiser.py           # PuLP squad optimiser + scenarios
│   ├── recommend.py           # Buy/Retain/Release table
│   ├── economics.py           # P&L logic mirrored from Excel
│   └── build_excel.py / build_deck.py
├── notebooks/                 # 01_eda ... 06_recommendations
├── app/
│   ├── Home.py                # Executive summary
│   └── pages/                 # 1_Economics.py ... 5_Recommendations.py
├── outputs/
│   ├── excel/                 # franchise_model.xlsx, squad_optimiser.xlsx
│   ├── deck/                  # draft deck .pptx
│   └── charts/
├── docs/
│   ├── methodology.md
│   └── sources.md
└── tests/
```

---

## 5. Data Sources

1. **Cricsheet** (cricsheet.org → Downloads → IPL): ball-by-ball data for every IPL match. Prefer the CSV (csv2) format; JSON is also fine. Also download the Cricsheet **people register** for player identifiers.
2. **Auction prices**: compiled from Wikipedia's IPL personnel-change tables for 2022-2026 (which cite ESPNcricinfo / IPLT20) into `data/raw/auction/`, with every source logged in `docs/sources.md`.
   - Target schema: `season, player_name, team, role, nationality, overseas (bool), capped (bool), base_price_lakh, sold_price_lakh, status (sold/unsold/retained)`
3. **Player name matching**: auction names and Cricsheet names differ. Build a mapping table (`data/processed/player_map.csv`) using fuzzy matching + a manual-override CSV. Report unmatched players rather than silently dropping them.
4. **Franchise economics**: public figures only (IPL media rights deal, brand valuation reports, sponsorship news). Everything else is an assumption in `config/assumptions.yaml`.
5. **IPL rules**: official IPL site or reliable news, checked for the target auction.

---

## 6. Build Phases (with acceptance criteria)

### Phase 1 — Setup & Data Pipeline
- Create repo structure, `requirements.txt`, config files.
- `ingest.py`: load Cricsheet data into one ball-level table with: match_id, season, date, venue, batting_team, bowling_team, innings, over, ball, batter, bowler, runs_batter, extras (by type), total_runs, wicket (bool), wicket_kind, player_dismissed.
- `features.py`: add **phase** column: Powerplay (overs 1–6), Middle (7–15), Death (16–20). Handle super overs (exclude) and rain-shortened matches (flag).
- Load and clean auction data; build player name mapping.

**Acceptance:** match count per season matches Cricsheet totals; no duplicate balls; mapping report shows % of auction players matched (target ≥ 90% for recent seasons); tests pass.

### Phase 2 — Franchise Economics Model (Excel + Python mirror)
Build `outputs/excel/franchise_model.xlsx` with sheets:
- **Assumptions**: every input with value, unit, source/reason.
- **P&L**: Revenue — central media rights share, central sponsorship share, team sponsorships, ticketing (home matches × capacity × occupancy × avg price), merchandise, prize money. Costs — player salaries, franchise fee (if applicable), operations, marketing, travel.
- **Scenarios**: "Missed playoffs" vs "Made playoffs" vs "Won title" — show how revenue changes (extra home matches, prize money, sponsor/merch uplift assumption).
- All calculated cells use Excel formulas referencing the Assumptions sheet.

`economics.py` mirrors the same logic so the app can use sliders.

**Acceptance:** changing any assumption in Excel updates the P&L; Python and Excel give the same result for the base case; key insight written in `docs/methodology.md` (e.g. "X% of revenue is fixed central income; performance mainly moves Y").

### Phase 3 — Player Valuation (Impact Score)
In `valuation.py`, all parameters in `config/valuation.yaml`:

- **Baseline**: for each season and phase, league-average runs per ball.
- **Batting impact** = Σ (runs off ball − phase baseline) − (dismissals × wicket_cost[phase]).
- **Bowling impact** = Σ (phase baseline − runs conceded, excluding byes/leg-byes) + (wickets × wicket_value[phase]).
- `wicket_cost` / `wicket_value`: derive from data (e.g. average runs lost per wicket in that phase) and document the method.
- **Per-season score** = batting + bowling impact, expressed per match.
- **Small-sample shrinkage**: `adjusted = raw × n / (n + k)` where n = balls faced/bowled, k configurable (e.g. 120).
- **Recency weighting** across last 3 seasons (e.g. 0.5 / 0.3 / 0.2, configurable).
- Also compute: consistency (std dev across seasons), phase-wise breakdown, games-played availability.
- Age: include if reliable birth-date data is available; otherwise leave out and note it as a limitation.

**Acceptance:** top-20 players by impact look sensible to a cricket fan (sanity check list printed in notebook); each component explained in `methodology.md`; unit tests for the formulas on a tiny hand-made dataset.

### Phase 4 — Market Inefficiency Analysis
In `market.py`:
- Fit a simple model of auction price on impact score (plus overseas and capped flags). Keep it explainable (linear regression on log price is fine).
- **Fair value** = model-predicted price. **Mispricing %** = (fair value − actual price) / actual price.
- Aggregate mispricing by **role** and **phase specialism** to find patterns (e.g. "death bowlers are underpriced by X%").
- **Bid ceiling** = fair value × (1 + strategic premium if the player fills a red gap role). Premium configurable.

**Acceptance:** scatter plot of impact vs price with under/overpriced players highlighted; a written list of the top 3 market insights with numbers; model limitations noted (sample size, auction dynamics, missing variables).

### Phase 5 — Squad Gap Analysis
In `squad.py`:
- Classify every player into roles from data: Opener, Anchor, Middle-order, Finisher, Wicketkeeper, Powerplay pacer, Death pacer, Wrist spinner, Finger spinner, All-rounder. Rules must be data-driven (e.g. share of balls faced in Death phase for finishers) and documented. Allow manual overrides via CSV.
- For [FRANCHISE NAME]'s retained squad, build a **role coverage matrix**: for each role, best available player's impact vs league benchmark → Green / Amber / Red.

**Acceptance:** matrix chart exported to `outputs/charts/`; every Red role has a one-line explanation.

### Phase 6 — Squad Optimiser + Scenarios
In `optimiser.py` using PuLP (binary decision variable per auction-pool player; retained players fixed):

- **Objective**: maximise Σ (impact_i × role_need_weight_i × x_i), where role_need_weight is higher for Red/Amber roles.
- **Constraints** (values from `config/rules.yaml`):
  - Σ expected_cost_i × x_i ≤ remaining purse
  - squad size within min/max
  - overseas players ≤ cap
  - minimum count per role (configurable)
  - locked players (must buy) and excluded players (must not buy)
- **expected_cost_i** = fair value × (1 + rival_inflation %)
- **Scenarios**:
  - *Win Now*: heavier recency weights, no age penalty
  - *Long-Term Build*: age penalty for older players (if age data exists), bonus for younger players
  - *Rival Inflation*: re-run at +10%, +20%, +30% prices
- Output: selected squad, purse used, roles covered, total impact vs current squad.
- Build `outputs/excel/squad_optimiser.xlsx`: same problem set up for **Excel Solver** on a reduced candidate pool (e.g. top 60 candidates), with instructions sheet explaining how to run Solver.

**Acceptance:** optimiser always respects all constraints (write tests for this); Python and Excel Solver give the same or near-same squad on the reduced pool; scenario comparison table produced.

### Phase 7 — Recommendations + Impact Estimate
In `recommend.py`, produce the final **recommendations table**:

| Player | Action (Buy/Retain/Release) | Role | Impact score | Fair value | Bid ceiling | Rationale (1 line) | Risk (1 line) | Backup option |

- Rationale must cite a number (e.g. "Top-5 death economy over 3 seasons; 40% below comparable players").
- Every Buy has a backup player of similar role within budget.
- **Impact estimate**: translate the squad strength gain into an estimated change in win probability / playoff chance (simple, documented method, e.g. regression of team win % on total squad impact across seasons), then feed that into the Phase 2 P&L scenarios to show revenue impact.

**Acceptance:** table exported to CSV and Excel; impact chain (squad strength → wins → playoffs → revenue) documented with its assumptions.

### Phase 8 — Streamlit App: "Auction War Room"
Multipage app in `app/`, reading only from `data/processed/` and `src/` modules. Use `st.cache_data` for loading.

1. **Home — Executive Summary**: the key recommendation in 2–3 sentences, 4 metric cards (purse used, squad strength gain, # targets, projected playoff chance change), one headline chart.
2. **Franchise Economics**: sliders for key assumptions (ticket price, occupancy, playoff scenario, sponsorship uplift) → live P&L and revenue breakdown chart.
3. **Player Market Explorer**: interactive plotly scatter (impact vs price), filters for role, phase, overseas, season; hover shows player card; table of most under/overpriced players.
4. **Squad Gap Matrix**: colour grid for the franchise; click/select a role to see the best market options for it.
5. **Auction Simulator**: inputs for purse, strategy (Win Now / Long-Term), rival inflation %, locked players, excluded players → "Optimise" button runs PuLP → shows selected squad, purse used, roles covered, comparison with current squad.
6. **Recommendations**: the Buy/Retain/Release table with filters + download buttons for CSV, the Excel models, and the deck.

Design rules: clean layout, 2–3 colours max, every page title states its key takeaway as a sentence, an expandable "Assumptions & method" section on each page, works on mobile widths.

**Acceptance:** app runs locally with `streamlit run app/Home.py`; optimiser runs in under ~10 seconds; deployed to Streamlit Community Cloud with the link added to README.

### Phase 9 — Draft Deck + README
`build_deck.py` (python-pptx) produces a clean draft deck using charts from `outputs/charts/`. **Action titles** (full-sentence insights) on every slide:

1. Executive summary (answer first)
2. Situation & key question
3. How the franchise makes money
4. What wins IPL matches
5. Where the auction market misprices players
6. Our squad gaps
7. Recommended auction strategy
8. Player recommendations
9. Scenarios & bid ceilings
10. Expected impact on wins and revenue
11. Risks & mitigations
12. Next steps
13. Appendix: methodology & assumptions

**README**: opens with the key question, answer, and 3 headline insights; then app link, deck link, screenshots, how to run, methodology summary, limitations, data sources.

**Acceptance:** deck opens cleanly; I will refine the final deck by hand. README understandable by a non-technical recruiter in 60 seconds.

---

## 7. Known Limitations to Document (be honest)

- Auction prices reflect bidding dynamics, not only player value.
- Impact score ignores fielding, captaincy, and match situation beyond phase.
- Small samples for new or uncapped players.
- Franchise financials are largely assumption-based.
- Past performance may not predict future performance (form, injury, age).

---

## 8. Definition of Done

- [ ] All 9 phases pass their acceptance criteria
- [ ] `docs/methodology.md` explains every method in plain English
- [ ] `docs/sources.md` lists every external figure with source and date
- [ ] Tests pass (`pytest`)
- [ ] App deployed and linked
- [ ] Excel models work with live formulas / Solver
- [ ] Draft deck generated
- [ ] README written as an executive summary

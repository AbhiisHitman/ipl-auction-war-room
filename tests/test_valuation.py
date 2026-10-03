"""Impact Score formulas on a tiny hand-made dataset (numbers checkable by hand)."""
import pandas as pd
import pytest

from src import valuation as V


def _base():
    # One season, two phases. League batters score 1.0 run/ball in the powerplay,
    # 2.0 at the death; batters get out once per 20 balls; bowler wickets 1 per 20.
    return pd.DataFrame({
        "season": [2026, 2026],
        "phase": ["Powerplay", "Death"],
        "bat_rpb": [1.0, 2.0],
        "bowl_rpb": [1.0, 2.0],
        "out_rate": [0.05, 0.05],
        "wkt_rate": [0.05, 0.05],
    })


def _wv():
    return pd.Series({"Powerplay": 10.0, "Middle": 5.0, "Death": 2.0})


def test_shrinkage_formula():
    assert V.shrink(10.0, 120, 120) == pytest.approx(5.0)  # half trust at n = k
    assert V.shrink(10.0, 0, 120) == 0.0                   # no balls -> league average
    assert V.shrink(10.0, 1080, 120) == pytest.approx(9.0)


def test_batting_impact_by_hand():
    # Batter: 20 powerplay balls, 30 runs, 1 dismissal, 1 match.
    # runs above baseline = 30 - 20*1.0 = 10
    # wickets above expected = 1 - 20*0.05 = 0  -> no wicket penalty
    bat = pd.DataFrame({"player": ["A"], "season": [2026], "phase": ["Powerplay"],
                        "balls_faced": [20], "runs": [30], "dismissals": [1]})
    bowl = pd.DataFrame(columns=["player", "season", "phase", "legal_balls", "runs_conceded", "wickets"])
    apps = pd.DataFrame({"player": ["A"], "season": [2026], "team": ["CSK"], "matches": [1]})
    season, _ = V.season_impact(bat, bowl, apps, _base(), _wv())
    assert season.loc[0, "bat_impact"] == pytest.approx(10.0)
    # shrunk per match: 10 * 20 / (20 + 120)
    assert season.loc[0, "bat_pm_adj"] == pytest.approx(10 * 20 / 140)


def test_extra_dismissal_costs_wicket_value():
    # Same batter but out 3 times: 2 extra dismissals x 10 runs = -20.
    bat = pd.DataFrame({"player": ["A"], "season": [2026], "phase": ["Powerplay"],
                        "balls_faced": [20], "runs": [30], "dismissals": [3]})
    bowl = pd.DataFrame(columns=["player", "season", "phase", "legal_balls", "runs_conceded", "wickets"])
    apps = pd.DataFrame({"player": ["A"], "season": [2026], "team": ["CSK"], "matches": [1]})
    season, _ = V.season_impact(bat, bowl, apps, _base(), _wv())
    assert season.loc[0, "bat_impact"] == pytest.approx(10 - 2 * 10)


def test_bowling_impact_by_hand():
    # Death bowler: 24 balls, 40 runs, 3 wickets.
    # runs saved = 24*2.0 - 40 = 8; extra wickets = 3 - 24*0.05 = 1.8 -> 1.8*2 = 3.6
    bat = pd.DataFrame(columns=["player", "season", "phase", "balls_faced", "runs", "dismissals"])
    bowl = pd.DataFrame({"player": ["B"], "season": [2026], "phase": ["Death"],
                         "legal_balls": [24], "runs_conceded": [40], "wickets": [3]})
    apps = pd.DataFrame({"player": ["B"], "season": [2026], "team": ["MI"], "matches": [2]})
    season, _ = V.season_impact(bat, bowl, apps, _base(), _wv())
    assert season.loc[0, "bowl_impact"] == pytest.approx(8 + 3.6)
    assert season.loc[0, "bowl_pm"] == pytest.approx((8 + 3.6) / 2)


def test_league_average_player_scores_zero():
    bat = pd.DataFrame({"player": ["C"], "season": [2026], "phase": ["Death"],
                        "balls_faced": [100], "runs": [200], "dismissals": [5]})
    bowl = pd.DataFrame({"player": ["C"], "season": [2026], "phase": ["Death"],
                         "legal_balls": [100], "runs_conceded": [200], "wickets": [5]})
    apps = pd.DataFrame({"player": ["C"], "season": [2026], "team": ["RR"], "matches": [10]})
    season, _ = V.season_impact(bat, bowl, apps, _base(), _wv())
    assert season.loc[0, "impact_pm"] == pytest.approx(0.0)


def test_recency_weights_renormalise_for_missing_season():
    season = pd.DataFrame({
        "player": ["A", "A"], "season": [2026, 2024],
        "impact_pm": [10.0, 0.0], "bat_pm_adj": [10.0, 0.0], "bowl_pm_adj": [0.0, 0.0],
        "matches": [14, 14], "balls_faced": [300, 300], "balls_bowled": [0, 0],
    })
    phase_tab = pd.DataFrame({"player": ["A", "A"], "season": [2026, 2024],
                              "phase": ["Powerplay", "Powerplay"], "phase_pm": [10.0, 0.0]})
    out = V.weighted_impact(season, phase_tab, as_of=2027, weights=[0.5, 0.3, 0.2])
    # played 2026 (w=0.5) and 2024 (w=0.2): (0.5*10 + 0.2*0) / 0.7
    assert out.loc[0, "impact"] == pytest.approx(5 / 0.7)


def test_phase_baselines_simple():
    balls = pd.DataFrame({
        "match_id": [1, 1, 1, 1], "season": [2026] * 4, "phase": ["Powerplay"] * 4,
        "runs_batter": [4, 0, 1, 0], "bowler_runs": [4, 1, 1, 0],
        "ball_faced": [True, False, True, True], "legal_ball": [True, False, True, True],
        "wicket": [False, False, False, True], "bowler_wicket": [False, False, False, True],
    })
    b = V.phase_baselines(balls).iloc[0]
    assert b["bat_rpb"] == pytest.approx(5 / 3)     # wide is not a ball faced
    assert b["bowl_rpb"] == pytest.approx(6 / 3)    # wide runs charged to bowler
    assert b["out_rate"] == pytest.approx(1 / 3)

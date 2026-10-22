import numpy as np
import pandas as pd

from denguecast import config
from denguecast.scoring import interval_score, relative_wis, score_forecasts, wis

Q = np.array(config.QUANTILES)


def test_wis_zero_for_perfect_point():
    assert wis(Q, np.full(9, 50.0), 50.0) == 0.0


def test_wis_hand_computed():
    vals = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90], float)
    y = 95.0
    # median term 0.5*|95-50| = 22.5
    # alpha .05: (90-10) + 40*(95-90) = 280 -> *0.025 = 7.0
    # alpha .10: (80-20) + 20*(95-80) = 360 -> *0.05 = 18.0
    # alpha .20: (70-30) + 10*(95-70) = 290 -> *0.10 = 29.0
    # alpha .50: (60-40) + 4*(95-60) = 160 -> *0.25 = 40.0
    expected = (22.5 + 7 + 18 + 29 + 40) / 4.5
    assert np.isclose(wis(Q, vals, y), expected)


def test_wis_equals_mean_quantile_score_identity():
    rng = np.random.default_rng(1)
    for _ in range(200):
        vals = np.sort(rng.gamma(2, 50, 9))
        y = float(rng.gamma(2, 50))
        qs = sum(2 * ((y <= v) - t) * (v - y) for t, v in zip(Q, vals))
        assert np.isclose(wis(Q, vals, y), qs / len(Q))


def test_interval_score_inside_is_width():
    assert interval_score(10, 20, 15, 0.1) == 10


def test_score_and_relative_wis():
    f = pd.DataFrame({"unit": "X", "origin_week_end": "2023-01-07", "horizon": 1,
                      "target_week_end": "2023-01-14", "quantile": Q, "value": np.linspace(10, 90, 9)})
    truth = pd.DataFrame({"unit": ["X"], "week_end": ["2023-01-14"], "value": [50.0]})
    s = score_forecasts(f, truth)
    assert s["cov50"].iloc[0] == 1 and s["cov90"].iloc[0] == 1
    assert np.isclose(relative_wis(s, s), 1.0)
    missing = score_forecasts(f, truth.assign(value=np.nan))
    assert missing.empty  # missing truth is excluded, never imputed

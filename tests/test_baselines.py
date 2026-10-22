from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from denguecast import baselines, config


def _weekly(n=80, units=("A", "B"), seed=0, start=date(2022, 1, 8)):
    """SYNTHETIC weekly series."""
    rng = np.random.default_rng(seed)
    rows = []
    for u in units:
        level = 50.0
        for i in range(n):
            level = max(1.0, level * np.exp(rng.normal(0, 0.2)))
            rows.append({"unit": u, "week_end": start + timedelta(weeks=i), "value": round(level)})
    return pd.DataFrame(rows)


def test_persistence_median_is_last_value_and_quantiles_sorted():
    h = _weekly()
    origin = date(2022, 1, 8) + timedelta(weeks=60)
    fc = baselines.persistence(h, origin)
    last = h[(h.unit == "A") & (h.week_end == origin)]["value"].iloc[0]
    med = fc[(fc.unit == "A") & (fc.horizon == 1) & (fc["quantile"] == 0.5)]["value"].iloc[0]
    assert np.isclose(med, last)
    for _, g in fc.groupby(["unit", "horizon"]):
        assert (np.diff(g.sort_values("quantile")["value"].values) >= 0).all()
    assert len(fc) == 2 * len(config.HORIZONS) * len(config.QUANTILES)


def test_persistence_ignores_data_after_origin():
    h = _weekly()
    origin = date(2022, 1, 8) + timedelta(weeks=60)
    future = h["week_end"] > origin
    h2 = h.copy()
    h2.loc[future, "value"] = 10**6
    pd.testing.assert_frame_equal(baselines.persistence(h, origin), baselines.persistence(h2, origin))


def test_insufficient_history_raises():
    h = _weekly(n=5, units=("A",))
    with pytest.raises(baselines.InsufficientHistory):
        baselines.persistence(h, date(2022, 1, 8) + timedelta(weeks=4))


def test_seasonal_naive_uses_52_weeks_back():
    h = _weekly(n=110)
    origin = date(2022, 1, 8) + timedelta(weeks=100)
    fc = baselines.seasonal_naive(h, origin)
    target = pd.Timestamp(origin) + pd.Timedelta(weeks=1)
    ly = (target - pd.Timedelta(weeks=52)).date()
    expected = h[(h.unit == "A") & (h.week_end == ly)]["value"].iloc[0]
    med = fc[(fc.unit == "A") & (fc.horizon == 1) & (fc["quantile"] == 0.5)]["value"].iloc[0]
    assert np.isclose(med, expected)

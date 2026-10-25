"""Mechanics tests for week-2 models on SYNTHETIC data. These do not say
anything about forecast accuracy."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from denguecast import config, models


def _weekly(n=100, units=("A", "B", "C"), seed=0):
    rng = np.random.default_rng(seed)
    start = date(2022, 1, 8)
    rows = []
    for j, u in enumerate(units):
        for i in range(n):
            season = 20 + 300 * np.exp(-(((i % 52) - 36) / 6) ** 2)
            rows.append({"unit": u, "week_end": start + timedelta(weeks=i), "value": float(rng.poisson(season / (j + 1)))})
    return pd.DataFrame(rows)


ORIGIN = date(2022, 1, 8) + timedelta(weeks=90)


def _check(fc, n_units=3):
    assert len(fc) == n_units * len(config.HORIZONS) * len(config.QUANTILES)
    assert (fc["value"] >= 0).all()
    for _, g in fc.groupby(["unit", "horizon"]):
        assert (np.diff(g.sort_values("quantile")["value"].values) >= -1e-9).all()


def test_model_a_shape_sorted_and_deterministic():
    h = _weekly()
    a1, a2 = models.model_a(h, ORIGIN), models.model_a(h, ORIGIN)
    _check(a1)
    pd.testing.assert_frame_equal(a1, a2)


def test_model_a_ignores_future():
    h = _weekly()
    h2 = h.copy()
    h2.loc[pd.to_datetime(h2["week_end"]) > pd.Timestamp(ORIGIN), "value"] = 1e6
    pd.testing.assert_frame_equal(models.model_a(h, ORIGIN), models.model_a(h2, ORIGIN))


def test_b3_uses_fourier_with_under_three_seasons_and_ignores_future():
    h = _weekly()
    b = models.b3_arima(h, ORIGIN)
    _check(b)
    assert set(b["interval_basis"]) == {"arima_fourier"}
    h2 = h.copy()
    h2.loc[pd.to_datetime(h2["week_end"]) > pd.Timestamp(ORIGIN), "value"] = 1e6
    pd.testing.assert_frame_equal(b, models.b3_arima(h2, ORIGIN))


def test_ensemble_is_quantilewise_mean():
    h = _weekly()
    a, b = models.model_a(h, ORIGIN), models.b3_arima(h, ORIGIN)
    e = models.ensemble(a, b)
    _check(e)
    key = ["unit", "horizon", "quantile"]
    m = a.merge(b, on=key, suffixes=("_a", "_b")).merge(e, on=key)
    mean = (m["value_a"] + m["value_b"]) / 2
    # Equal to the mean wherever the averaged quantiles were already ordered.
    assert np.allclose(np.sort(mean.values), np.sort(m["value"].values))


def test_ensemble_rejects_mismatched_members():
    h = _weekly()
    a = models.model_a(h, ORIGIN)
    with pytest.raises(ValueError):
        models.ensemble(a, a[a["unit"] != "A"])


def test_model_a_fit_once_predict_later_uses_no_future():
    h = _weekly()
    fit_origin, later = ORIGIN - timedelta(weeks=3), ORIGIN
    fitted = models.fit_model_a(h, fit_origin)
    p1 = models.predict_model_a(fitted, h, later)
    _check(p1)
    # Changing data after the later origin must not change the forecast
    h2 = h.copy()
    h2.loc[pd.to_datetime(h2["week_end"]) > pd.Timestamp(later), "value"] *= 50
    pd.testing.assert_frame_equal(p1, models.predict_model_a(fitted, h2, later))
    # Predicting at the fit origin equals fit-and-predict at that origin
    pd.testing.assert_frame_equal(models.predict_model_a(fitted, h, fit_origin), models.model_a(h, fit_origin))
    with pytest.raises(ValueError):
        models.predict_model_a(fitted, h, fit_origin - timedelta(weeks=1))


def test_model_a_early_stopping_deterministic():
    h = _weekly()
    params = dict(n_estimators=200)
    f1 = models.fit_model_a(h, ORIGIN, params=params, early_stop_weeks=8, early_stop_rounds=10)
    f2 = models.fit_model_a(h, ORIGIN, params=params, early_stop_weeks=8, early_stop_rounds=10)
    assert f1["n_trees"] == f2["n_trees"] and max(f1["n_trees"].values()) <= 200
    pd.testing.assert_frame_equal(models.predict_model_a(f1, h, ORIGIN), models.predict_model_a(f2, h, ORIGIN))

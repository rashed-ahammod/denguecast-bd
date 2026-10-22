"""Model A, B3 and the ensemble (pre-registration Section 7).

STATUS: implemented and tested on SYNTHETIC data for mechanics only (shapes,
sorted quantiles, no use of data after the origin, determinism). Not yet
trained or evaluated on real data, and hyperparameters are not tuned.

Model A: LightGBM, quantile loss, one model per (horizon, quantile), pooled
across units, direct strategy. Weather and population features are optional
and are used only when provided (they are not ingested yet: blocker B1).

B3: per-unit ARIMA on log(1 + y). The pre-registration says SARIMA; a
52-week seasonal term cannot be estimated from the single 2022 training
season, so when fewer than MIN_SEASONS_FOR_SAR seasons are available the
annual cycle is modelled with Fourier regressors instead. This is proposed
deviation P3 (docs/ASSUMPTIONS_AND_BLOCKERS.md) and needs approval before lock.

Ensemble: equal-weight quantile-wise average of Model A and B3.
"""
from __future__ import annotations

import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.tsa.statespace.sarimax import SARIMAX

from . import config
from .baselines import FORECAST_COLS, InsufficientHistory

N_LAGS = 8
MIN_SEASONS_FOR_SAR = 3
LGB_PARAMS = dict(learning_rate=0.05, num_leaves=15, min_data_in_leaf=20, n_estimators=300,
                  feature_fraction=0.9, lambda_l2=1.0, seed=config.RANDOM_SEED, deterministic=True,
                  force_row_wise=True, num_threads=1, verbose=-1)


def _wide(history: pd.DataFrame, origin) -> pd.DataFrame:
    h = history.copy()
    h["week_end"] = pd.to_datetime(h["week_end"])
    h = h[h["week_end"] <= pd.Timestamp(origin)]
    wide = h.pivot_table(index="week_end", columns="unit", values="value").sort_index()
    # Regular weekly index so row shifts equal week shifts (gaps become NaN).
    return wide.asfreq("7D") if len(wide) else wide


def _features(wide_log: pd.DataFrame, unit_codes: dict[str, int], weather: pd.DataFrame | None) -> pd.DataFrame:
    """One row per (week, unit) using only that week and earlier weeks."""
    rows = []
    for u in wide_log.columns:
        s = wide_log[u]
        f = pd.DataFrame(index=s.index)
        for k in range(N_LAGS):
            f[f"lag{k + 1}"] = s.shift(k)  # lag1 = the week itself (the origin when predicting)
        f["growth2"] = s - s.shift(2)
        f["growth4"] = s - s.shift(4)
        f["missing"] = s.isna().astype(int)
        f["unit_code"] = unit_codes[u]
        f["unit"] = u
        rows.append(f)
    feats = pd.concat(rows).reset_index().rename(columns={"index": "week_end"})
    if weather is not None:
        feats = feats.merge(weather, on=["unit", "week_end"], how="left")
    return feats


def model_a(history: pd.DataFrame, origin, horizons=config.HORIZONS, quantiles=config.QUANTILES,
            weather: pd.DataFrame | None = None, params: dict | None = None) -> pd.DataFrame:
    origin = pd.Timestamp(origin)
    params = {**LGB_PARAMS, **(params or {})}
    wide = _wide(history, origin)
    if len(wide) < N_LAGS + max(horizons) + 10:
        raise InsufficientHistory(f"Model A needs more weeks of history (have {len(wide)})")
    wide_log = np.log1p(wide)
    unit_codes = {u: i for i, u in enumerate(sorted(wide.columns))}
    feats = _features(wide_log, unit_codes, weather)
    feat_cols = [c for c in feats.columns if c not in ("week_end", "unit")]
    pred_rows = feats[feats["week_end"] == origin]
    out = []
    for h in horizons:
        target = wide_log.shift(-h).stack(future_stack=True).rename("y").reset_index()
        target.columns = ["week_end", "unit", "y"]
        train = feats.merge(target, on=["week_end", "unit"]).dropna(subset=["y", "lag1"])
        # only targets observed by the origin: week_end + h <= origin
        train = train[train["week_end"] + pd.Timedelta(weeks=h) <= origin]
        if len(train) < 50:
            raise InsufficientHistory(f"Model A h={h}: only {len(train)} training rows")
        preds = []
        for q in quantiles:
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, **params)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                m.fit(train[feat_cols], train["y"], categorical_feature=["unit_code"])
            preds.append(m.predict(pred_rows[feat_cols]))
        vals = np.clip(np.sort(np.expm1(np.vstack(preds).T), axis=1), 0, None)
        for u, row in zip(pred_rows["unit"], vals):
            out += [dict(unit=u, origin_week_end=origin.date(), horizon=h,
                         target_week_end=(origin + pd.Timedelta(weeks=h)).date(), quantile=q, value=v,
                         interval_basis="model_a") for q, v in zip(quantiles, row)]
    return pd.DataFrame(out, columns=FORECAST_COLS)


def _fourier(index: pd.DatetimeIndex, k: int = 2) -> pd.DataFrame:
    t = index.dayofyear.values / 365.25
    return pd.DataFrame({f"{fn}{i}": f(2 * np.pi * i * t) for i in range(1, k + 1)
                         for fn, f in (("sin", np.sin), ("cos", np.cos))}, index=index)


def b3_arima(history: pd.DataFrame, origin, horizons=config.HORIZONS, quantiles=config.QUANTILES) -> pd.DataFrame:
    origin = pd.Timestamp(origin)
    wide = _wide(history, origin)
    out = []
    for u in wide.columns:
        s = np.log1p(wide[u]).asfreq("7D")
        if s.notna().sum() < 30 or pd.isna(s.iloc[-1]):
            raise InsufficientHistory(f"B3 {u}: need >=30 weeks and an origin value")
        n_seasons = s.notna().sum() / 52.0
        future_idx = pd.date_range(origin + pd.Timedelta(weeks=1), periods=max(horizons), freq="7D")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if n_seasons >= MIN_SEASONS_FOR_SAR:
                res = SARIMAX(s, order=(1, 1, 1), seasonal_order=(1, 0, 0, 52)).fit(disp=False)
                fc = res.get_forecast(max(horizons))
                variant = "sarima"
            else:
                res = SARIMAX(s, exog=_fourier(s.index), order=(1, 1, 1)).fit(disp=False)
                fc = res.get_forecast(max(horizons), exog=_fourier(future_idx))
                variant = "arima_fourier"
        mean, se = np.asarray(fc.predicted_mean), np.sqrt(np.asarray(fc.var_pred_mean))
        for h in horizons:
            vals = np.clip(np.sort(np.expm1(mean[h - 1] + norm.ppf(quantiles) * se[h - 1])), 0, None)
            out += [dict(unit=u, origin_week_end=origin.date(), horizon=h,
                         target_week_end=(origin + pd.Timedelta(weeks=h)).date(), quantile=q, value=v,
                         interval_basis=variant) for q, v in zip(quantiles, vals)]
    return pd.DataFrame(out, columns=FORECAST_COLS)


def ensemble(*forecasts: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight quantile-wise average; quantiles re-sorted per unit/horizon."""
    keys = ["unit", "origin_week_end", "horizon", "target_week_end", "quantile"]
    stacked = pd.concat([f[keys + ["value"]] for f in forecasts])
    counts = stacked.groupby(keys).size()
    if (counts != len(forecasts)).any():
        raise ValueError("ensemble members do not cover the same units/horizons/quantiles")
    avg = stacked.groupby(keys, as_index=False)["value"].mean()
    avg["value"] = avg.groupby(["unit", "horizon"])["value"].transform(lambda v: np.sort(v.values))
    avg["interval_basis"] = "ensemble"
    return avg[FORECAST_COLS]

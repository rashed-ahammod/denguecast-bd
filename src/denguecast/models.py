"""Model A, B3 and the ensemble (pre-registration Section 7).

Tested on SYNTHETIC data for mechanics (shapes, sorted quantiles, no use of
data after the origin, determinism, fit-once/predict-later). Real-data
results come from evaluate.py.

Model A: LightGBM, quantile loss, one model per (horizon, quantile), pooled
across units, direct strategy. Weather and population features are optional
and are used only when provided (not used for 26 October: D3).

B3: per-unit ARIMA on log(1 + y). The pre-registration says SARIMA; a
52-week seasonal term cannot be estimated from the single 2022 training
season, so when fewer than MIN_SEASONS_FOR_SAR seasons are available the
annual cycle is modelled with Fourier regressors instead. This is amendment
D4 (P3 in docs/ASSUMPTIONS_AND_BLOCKERS.md).

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


def fit_model_a(history: pd.DataFrame, origin, horizons=config.HORIZONS, quantiles=config.QUANTILES,
                weather: pd.DataFrame | None = None, params: dict | None = None,
                early_stop_weeks: int | None = None, early_stop_rounds: int = 100) -> dict:
    """Fit one LightGBM quantile model per (horizon, quantile) on data up to origin.

    With ``early_stop_weeks``, the number of trees is chosen by early stopping
    on the rows whose target week falls in the last ``early_stop_weeks`` weeks
    before origin; the model is then refitted on all rows with that many trees.
    Everything used is at or before origin."""
    origin = pd.Timestamp(origin)
    params = {**LGB_PARAMS, **(params or {})}
    wide = _wide(history, origin)
    if len(wide) < N_LAGS + max(horizons) + 10:
        raise InsufficientHistory(f"Model A needs more weeks of history (have {len(wide)})")
    wide_log = np.log1p(wide)
    unit_codes = {u: i for i, u in enumerate(sorted(wide.columns))}
    feats = _features(wide_log, unit_codes, weather)
    feat_cols = [c for c in feats.columns if c not in ("week_end", "unit")]
    fitted = {"origin": origin, "unit_codes": unit_codes, "feat_cols": feat_cols, "models": {}, "n_trees": {},
              "horizons": list(horizons), "quantiles": list(quantiles)}
    for h in horizons:
        target = wide_log.shift(-h).stack(future_stack=True).rename("y").reset_index()
        target.columns = ["week_end", "unit", "y"]
        train = feats.merge(target, on=["week_end", "unit"]).dropna(subset=["y", "lag1"])
        # only targets observed by the origin: week_end + h <= origin
        train = train[train["week_end"] + pd.Timedelta(weeks=h) <= origin]
        if len(train) < 50:
            raise InsufficientHistory(f"Model A h={h}: only {len(train)} training rows")
        for q in quantiles:
            p = dict(params)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                if early_stop_weeks:
                    cut = origin - pd.Timedelta(weeks=early_stop_weeks)
                    is_val = train["week_end"] + pd.Timedelta(weeks=h) > cut
                    if not is_val.any() or is_val.all():
                        raise InsufficientHistory(f"Model A h={h}: no recent weeks to early-stop on before {origin.date()}")
                    m = lgb.LGBMRegressor(objective="quantile", alpha=q, **p)
                    m.fit(train.loc[~is_val, feat_cols], train.loc[~is_val, "y"], categorical_feature=["unit_code"],
                          eval_set=[(train.loc[is_val, feat_cols], train.loc[is_val, "y"])],
                          callbacks=[lgb.early_stopping(early_stop_rounds, verbose=False)])
                    p["n_estimators"] = max(int(m.best_iteration_ or p["n_estimators"]), 1)
                m = lgb.LGBMRegressor(objective="quantile", alpha=q, **p)
                m.fit(train[feat_cols], train["y"], categorical_feature=["unit_code"])
            fitted["models"][(h, q)] = m
            fitted["n_trees"][(h, q)] = p["n_estimators"]
    return fitted


def predict_model_a(fitted: dict, history: pd.DataFrame, origin, weather: pd.DataFrame | None = None) -> pd.DataFrame:
    """Forecast at ``origin`` (>= the fit origin) with a fitted Model A, using
    features built from history up to origin. Units unseen at fit time are skipped."""
    origin = pd.Timestamp(origin)
    if origin < fitted["origin"]:
        raise ValueError("cannot predict at an origin before the fit origin")
    wide = _wide(history, origin)
    wide = wide[[u for u in wide.columns if u in fitted["unit_codes"]]]
    feats = _features(np.log1p(wide), fitted["unit_codes"], weather)
    pred_rows = feats[feats["week_end"] == origin]
    out = []
    for h in fitted["horizons"]:
        preds = [fitted["models"][(h, q)].predict(pred_rows[fitted["feat_cols"]]) for q in fitted["quantiles"]]
        vals = np.clip(np.sort(np.expm1(np.vstack(preds).T), axis=1), 0, None)
        for u, row in zip(pred_rows["unit"], vals):
            out += [dict(unit=u, origin_week_end=origin.date(), horizon=h,
                         target_week_end=(origin + pd.Timedelta(weeks=h)).date(), quantile=q, value=v,
                         interval_basis="model_a") for q, v in zip(fitted["quantiles"], row)]
    return pd.DataFrame(out, columns=FORECAST_COLS)


def model_a(history: pd.DataFrame, origin, horizons=config.HORIZONS, quantiles=config.QUANTILES,
            weather: pd.DataFrame | None = None, params: dict | None = None) -> pd.DataFrame:
    """Fit at origin and forecast from origin."""
    fitted = fit_model_a(history, origin, horizons, quantiles, weather, params)
    return predict_model_a(fitted, history, origin, weather)


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

"""Scoring (pre-registration Section 9).

WIS = 1/(K + 1/2) * ( 1/2 |y - m| + sum_k alpha_k/2 * IS_alpha_k ),
IS_alpha = (u - l) + 2/alpha (l - y) 1[y < l] + 2/alpha (y - u) 1[y > u],
with alpha = 0.05, 0.10, 0.20, 0.50 (K = 4) read from the 9 quantiles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _q(levels: np.ndarray, values: np.ndarray, level: float) -> float:
    idx = np.where(np.isclose(levels, level))[0]
    if len(idx) != 1:
        raise ValueError(f"quantile {level} missing or duplicated")
    return float(values[idx[0]])


def interval_score(lower: float, upper: float, y: float, alpha: float) -> float:
    return (upper - lower) + (2 / alpha) * max(lower - y, 0) + (2 / alpha) * max(y - upper, 0)


def wis(levels, values, y: float, alphas=config.ALPHAS) -> float:
    levels, values = np.asarray(levels, float), np.asarray(values, float)
    m = _q(levels, values, 0.5)
    total = 0.5 * abs(y - m)
    for a in alphas:
        lo, hi = _q(levels, values, a / 2), _q(levels, values, 1 - a / 2)
        total += (a / 2) * interval_score(lo, hi, y, a)
    return total / (len(alphas) + 0.5)


def score_forecasts(forecasts: pd.DataFrame, truth: pd.DataFrame, log_scale: bool = False) -> pd.DataFrame:
    """forecasts: unit, origin_week_end, horizon, target_week_end, quantile, value
    truth: unit, week_end, value (rows with NaN truth are dropped and counted).
    Returns one row per forecast with wis, abs_error, cov50, cov90."""
    t = truth.rename(columns={"week_end": "target_week_end", "value": "y"}).copy()
    t["target_week_end"] = pd.to_datetime(t["target_week_end"]).dt.date
    f = forecasts.copy()
    f["target_week_end"] = pd.to_datetime(f["target_week_end"]).dt.date
    merged = f.merge(t[["unit", "target_week_end", "y"]], on=["unit", "target_week_end"], how="left")
    out = []
    for key, g in merged.groupby(["unit", "origin_week_end", "horizon", "target_week_end"]):
        y = g["y"].iloc[0]
        if pd.isna(y):
            continue
        lv, vals = g["quantile"].values, g["value"].values.astype(float)
        if log_scale:
            vals, y = np.log1p(vals), np.log1p(y)
        out.append(dict(
            unit=key[0], origin_week_end=key[1], horizon=key[2], target_week_end=key[3], y=y,
            wis=wis(lv, vals, y),
            abs_error=abs(y - _q(lv, vals, 0.5)),
            cov50=float(_q(lv, vals, 0.25) <= y <= _q(lv, vals, 0.75)),
            cov90=float(_q(lv, vals, 0.05) <= y <= _q(lv, vals, 0.95)),
        ))
    return pd.DataFrame(out)


def relative_wis(model_scores: pd.DataFrame, comparator_scores: pd.DataFrame) -> float:
    """Mean model WIS / mean comparator WIS over forecasts both have scored."""
    keys = ["unit", "origin_week_end", "horizon"]
    m = model_scores[keys + ["wis"]].merge(comparator_scores[keys + ["wis"]], on=keys, suffixes=("_m", "_c"))
    if m.empty:
        raise ValueError("no common scored forecasts")
    return float(m["wis_m"].mean() / m["wis_c"].mean())

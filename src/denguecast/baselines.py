"""Baselines B1 (persistence) and B2 (seasonal naive), pre-registration Section 7.

Both produce the 9 pre-registered quantiles. Intervals come from the empirical
distribution of past log ratios, re-centred so the median equals the
baseline's point forecast (assumption A7). Only weeks up to the origin are
used. If a unit has fewer than MIN_RATIOS usable ratios, ratios pooled across
all units are used; if the pool is also too small, InsufficientHistory is
raised rather than inventing an interval.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

MIN_RATIOS = 20
FORECAST_COLS = ["unit", "origin_week_end", "horizon", "target_week_end", "quantile", "value", "interval_basis"]


class InsufficientHistory(RuntimeError):
    pass


def _series(history: pd.DataFrame, unit: str, origin) -> pd.Series:
    g = history[(history["unit"] == unit)].copy()
    g["week_end"] = pd.to_datetime(g["week_end"])
    g = g[g["week_end"] <= pd.Timestamp(origin)]
    return g.set_index("week_end")["value"].sort_index().astype(float)


def _quantiles_from_ratios(center_log: float, ratios: np.ndarray, quantiles: list[float]) -> np.ndarray:
    q = np.quantile(ratios, quantiles)
    q = q - np.median(ratios)  # re-centre: median forecast = point forecast
    vals = np.expm1(center_log + q)
    return np.clip(np.sort(vals), 0, None)


def _pick_ratios(per_unit: dict[str, np.ndarray], unit: str) -> tuple[np.ndarray, str]:
    own = per_unit.get(unit, np.array([]))
    if len(own) >= MIN_RATIOS:
        return own, "unit"
    pooled = np.concatenate([v for v in per_unit.values()]) if per_unit else np.array([])
    if len(pooled) >= MIN_RATIOS:
        return pooled, "pooled"
    raise InsufficientHistory(f"only {len(own)} unit / {len(pooled)} pooled ratios for {unit}")


def persistence(history: pd.DataFrame, origin, units: list[str] | None = None,
                horizons=config.HORIZONS, quantiles=config.QUANTILES, on_missing: str = "raise") -> pd.DataFrame:
    """B1: every horizon equals the last observed week (the origin week).
    on_missing="skip" leaves out units with no value at the origin week and
    lists them in result.attrs["skipped_units"]."""
    origin = pd.Timestamp(origin)
    units = units or sorted(history["unit"].unique())
    rows = []
    skipped: set[str] = set()
    for h in horizons:
        per_unit = {}
        for u in units:
            s = _series(history, u, origin)
            lg = np.log1p(s)
            # ratio between week w+h and week w, both observed and both <= origin
            r = (lg.shift(-h, freq="7D").reindex(lg.index) - lg).dropna()
            per_unit[u] = r.values
        for u in units:
            s = _series(history, u, origin)
            if origin not in s.index or pd.isna(s.get(origin)):
                if on_missing == "skip":
                    skipped.add(u)
                    continue
                raise InsufficientHistory(f"{u}: no observed value for origin week {origin.date()}")
            ratios, basis = _pick_ratios(per_unit, u)
            qv = _quantiles_from_ratios(np.log1p(s[origin]), ratios, quantiles)
            target = origin + pd.Timedelta(weeks=h)
            rows += [dict(unit=u, origin_week_end=origin.date(), horizon=h, target_week_end=target.date(),
                          quantile=q, value=v, interval_basis=basis) for q, v in zip(quantiles, qv)]
    out = pd.DataFrame(rows, columns=FORECAST_COLS)
    out.attrs["skipped_units"] = sorted(skipped)
    return out


def seasonal_naive(history: pd.DataFrame, origin, units: list[str] | None = None,
                   horizons=config.HORIZONS, quantiles=config.QUANTILES) -> pd.DataFrame:
    """B2: each target week equals the same epi week one season earlier
    (52 weeks back). Intervals from log ratios y_t / y_{t-52w} observed up to origin."""
    origin = pd.Timestamp(origin)
    units = units or sorted(history["unit"].unique())
    per_unit = {}
    for u in units:
        lg = np.log1p(_series(history, u, origin))
        lag52 = lg.shift(52, freq="7D").reindex(lg.index)
        per_unit[u] = (lg - lag52).dropna().values
    rows = []
    for u in units:
        s = _series(history, u, origin)
        ratios, basis = _pick_ratios(per_unit, u)
        for h in horizons:
            target = origin + pd.Timedelta(weeks=h)
            last_year = target - pd.Timedelta(weeks=52)
            if last_year not in s.index or pd.isna(s.get(last_year)):
                raise InsufficientHistory(f"{u}: no value for {last_year.date()} (52 weeks before target)")
            qv = _quantiles_from_ratios(np.log1p(s[last_year]), ratios, quantiles)
            rows += [dict(unit=u, origin_week_end=origin.date(), horizon=h, target_week_end=target.date(),
                          quantile=q, value=v, interval_basis=basis) for q, v in zip(quantiles, qv)]
    return pd.DataFrame(rows, columns=FORECAST_COLS)

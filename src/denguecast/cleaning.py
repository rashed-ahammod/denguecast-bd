"""Cleaning and reconciliation rules (pre-registration Section 5).

Rule numbers in docstrings match the pre-registration. Every function is
causal: nothing here uses information from after the week being processed,
except ``final_truth``, which is used only for scoring.
Every action is reported to a QualityLog so it can be published.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from . import archive, config
from .epiweek import add_epiweek_columns

SOURCE_PRIORITY = ["dghs_dashboard_epiweek", "dghs_press_release", "who_searo_bulletin", "newspaper"]
WEEKLY_COLS = ["unit", "epi_year", "epi_week", "week_end", "value", "flag"]


@dataclass
class QualityLog:
    entries: list[dict] = field(default_factory=list)

    def add(self, rule: str, unit: str, key: str, action: str, detail: str = "") -> None:
        self.entries.append({"rule": rule, "unit": unit, "key": key, "action": action, "detail": detail})

    def write(self, path=None) -> None:
        path = path or config.QUALITY_LOG_FILE
        if not self.entries:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        stamp = archive.utc_now().isoformat()
        with path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["logged_at", "rule", "unit", "key", "action", "detail"])
            if new:
                w.writeheader()
            for e in self.entries:
                w.writerow({"logged_at": stamp, **e})


# ------------------------------------------------------------------ rule 2-4
def daily_to_weekly(daily: pd.DataFrame, log: QualityLog, cumulative: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rules 2-4. ``daily`` has columns unit, reference_date, value (admissions,
    NaN where missing). ``cumulative`` (optional) has unit, reference_date,
    value = year-to-date admissions after that day's report.

    Rule 3: a run of missing days is recovered from cumulative totals when the
    cumulative count is known just before the gap and on the first reported
    day after it (same calendar year). The recovered total is split across
    epi weeks in proportion to the number of missing days in each.
    Rule 4: otherwise affected weeks stay missing (value NaN, flag 'missing').
    """
    frames = []
    cum_lookup = {}
    if cumulative is not None and not cumulative.empty:
        for r in cumulative.itertuples():
            if pd.notna(r.value):
                cum_lookup[(r.unit, str(r.reference_date))] = float(r.value)
    for unit, g in daily.groupby("unit"):
        g = g.copy()
        g["reference_date"] = pd.to_datetime(g["reference_date"]).dt.date
        g = g.set_index("reference_date").sort_index()
        full_days = pd.date_range(g.index.min(), g.index.max(), freq="D").date
        s = g["value"].reindex(full_days).astype(float)
        recovered = pd.Series(0.0, index=s.index)
        unrecoverable = pd.Series(False, index=s.index)
        missing = s.isna()
        # find runs of missing days
        run = []
        for d in list(s.index) + [None]:
            if d is not None and missing.get(d, False):
                run.append(d)
                continue
            if run:
                before, after = run[0] - timedelta(days=1), d
                key_b, key_a = (unit, str(before)), (unit, str(after)) if after else (unit, "")
                if (
                    after is not None and key_b in cum_lookup and key_a in cum_lookup
                    and before.year == after.year and pd.notna(s.get(after))
                ):
                    gap_total = cum_lookup[key_a] - cum_lookup[key_b] - s[after]
                    if gap_total < 0:
                        unrecoverable.loc[run] = True
                        log.add("3", unit, f"{run[0]}..{run[-1]}", "not recovered", f"negative gap total {gap_total}")
                    else:
                        per_day = gap_total / len(run)
                        recovered.loc[run] = per_day
                        log.add("3", unit, f"{run[0]}..{run[-1]}", "recovered from cumulative", f"total {gap_total:g} over {len(run)} days")
                else:
                    unrecoverable.loc[run] = True
                    log.add("4", unit, f"{run[0]}..{run[-1]}", "left missing", f"{len(run)} day(s), no cumulative on both sides")
                run = []
        day = pd.DataFrame({"reference_date": s.index, "value": s.fillna(0.0) + recovered,
                            "recovered": recovered > 0, "unrecoverable": unrecoverable})
        day = add_epiweek_columns(day)
        wk = day.groupby(["epi_year", "epi_week", "week_end"], as_index=False).agg(
            value=("value", "sum"), recovered=("recovered", "any"), unrecoverable=("unrecoverable", "any"), n_days=("value", "size"))
        # Partial weeks at the edges of the series are incomplete, not zero.
        wk["flag"] = np.where(wk["unrecoverable"] | (wk["n_days"] < 7), "missing",
                              np.where(wk["recovered"], "recovered", ""))
        wk.loc[wk["flag"] == "missing", "value"] = np.nan
        wk["unit"] = unit
        frames.append(wk[WEEKLY_COLS])
    if not frames:
        return pd.DataFrame(columns=WEEKLY_COLS)
    return pd.concat(frames, ignore_index=True).sort_values(["unit", "week_end"]).reset_index(drop=True)


def add_feature_columns(weekly: pd.DataFrame) -> pd.DataFrame:
    """Rule 4 for model inputs: carry the last observed value forward (past
    only) and add a missing-data indicator. Scoring targets are untouched."""
    out = weekly.sort_values(["unit", "week_end"]).copy()
    out["missing"] = out["value"].isna().astype(int)
    out["value_ff"] = out.groupby("unit")["value"].ffill()
    return out


# -------------------------------------------------------------------- rule 7
def consistency_check(weekly: pd.DataFrame, log: QualityLog, tolerance: float = 0.02) -> pd.DataFrame:
    """Flag weeks where subnational units do not sum to NATIONAL within 2%."""
    nat = weekly[weekly["unit"] == "NATIONAL"].set_index("week_end")["value"]
    sub = weekly[weekly["unit"] != "NATIONAL"].groupby("week_end")["value"].sum(min_count=1)
    rows = []
    for wk, n in nat.items():
        s = sub.get(wk, np.nan)
        if pd.isna(n) or pd.isna(s) or n == 0:
            continue
        diff = abs(s - n) / n
        if diff > tolerance:
            log.add("7", "NATIONAL", str(wk), "flagged", f"units sum {s:g} vs national {n:g} ({diff:.1%})")
            rows.append({"week_end": wk, "units_sum": s, "national": n, "rel_diff": diff})
    return pd.DataFrame(rows, columns=["week_end", "units_sum", "national", "rel_diff"])


# -------------------------------------------------------------------- rule 8
def merge_city_corporations_if_incomplete(weekly: pd.DataFrame, log: QualityLog) -> pd.DataFrame:
    """For any epi year in which DNCC or DSCC has no data at all, combine the
    city corporation rows into one DHAKA_CITY unit for that year."""
    out = []
    for year, g in weekly.groupby("epi_year"):
        units = set(g.loc[g["value"].notna(), "unit"])
        has_n, has_s = "DNCC" in units, "DSCC" in units
        if has_n and has_s:
            out.append(g)
            continue
        city = g[g["unit"].isin(["DNCC", "DSCC", config.MERGED_DHAKA_CITY])]
        rest = g[~g["unit"].isin(["DNCC", "DSCC", config.MERGED_DHAKA_CITY])]
        if not city.empty:
            merged = city.groupby(["epi_year", "epi_week", "week_end"], as_index=False).agg(
                value=("value", lambda v: v.sum(min_count=1)), flag=("flag", lambda f: ";".join(sorted(set(x for x in f if x)))))
            merged["unit"] = config.MERGED_DHAKA_CITY
            out.append(pd.concat([rest, merged[WEEKLY_COLS]]))
            log.add("8", config.MERGED_DHAKA_CITY, str(year), "merged DNCC+DSCC", f"DNCC present={has_n}, DSCC present={has_s}")
        else:
            out.append(rest)
    return pd.concat(out, ignore_index=True).sort_values(["unit", "week_end"]).reset_index(drop=True)


# -------------------------------------------------------------------- rule 9
def flag_outliers(weekly: pd.DataFrame, log: QualityLog, window: int = 8, k: float = 5.0) -> pd.DataFrame:
    """Trailing (past-only) median/MAD check. Adds 'outlier' and 'value_clipped'.
    The original 'value' (scoring truth) is never changed. A MAD of 0 is
    floored at 1 so flat low-count series do not flag every change."""
    out = weekly.sort_values(["unit", "week_end"]).copy()
    out["outlier"] = False
    out["value_clipped"] = out["value"]
    for unit, idx in out.groupby("unit").groups.items():
        v = out.loc[idx, "value"]
        med = v.shift(1).rolling(window, min_periods=window).median()
        mad = v.shift(1).rolling(window, min_periods=window).apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
        mad = mad.clip(lower=1.0)
        lo, hi = (med - k * mad).clip(lower=0), med + k * mad
        is_out = (v < lo) | (v > hi)
        out.loc[idx, "outlier"] = is_out.fillna(False).values
        out.loc[idx, "value_clipped"] = np.where(is_out.fillna(False), v.clip(lo, hi), v)
        for i in v.index[is_out.fillna(False)]:
            log.add("9", unit, str(out.at[i, "week_end"]), "flagged outlier", f"value {v[i]:g}, bounds [{lo[i]:g}, {hi[i]:g}]")
    return out


# --------------------------------------------------------------- rules 5, 6
def final_truth(unit: str, week_end_date, metric: str, evaluated_at, **get_data_kwargs) -> tuple[float, bool]:
    """Rule 5 and 6. Truth for an epi week = its weekly value as known 14 days
    after the week ends, taking sources in priority order. Returns
    (value, provisional). Provisional = evaluated before the 14 days passed."""
    week_end_date = pd.Timestamp(week_end_date).date()
    target_time = pd.Timestamp(week_end_date + timedelta(days=14), tz="UTC") + pd.Timedelta(hours=23, minutes=59)
    eval_t = archive.to_utc(evaluated_at)
    provisional = eval_t < target_time
    as_of = min(target_time, eval_t)
    for src in SOURCE_PRIORITY:
        df = archive.get_data(as_of=as_of, metrics=[metric], units=[unit], period="epiweek", sources=[src], **get_data_kwargs)
        hit = df[df["reference_date"] == str(week_end_date)]
        if not hit.empty and pd.notna(hit["value"].iloc[0]):
            return float(hit["value"].iloc[0]), provisional
    return float("nan"), provisional


# ------------------------------------------------------------------- rule 10
def revision_summary(first_and_later: pd.DataFrame) -> pd.DataFrame:
    """Rule 10. Input columns: unit, week_end, first_value, value_1w, value_2w,
    value_4w (values as known 0/1/2/4 weeks after first publication). Returns
    median absolute relative revision by lag."""
    out = {}
    for lag in ("value_1w", "value_2w", "value_4w"):
        ok = first_and_later[[lag, "first_value"]].dropna()
        ok = ok[ok["first_value"] > 0]
        out[lag] = float(np.median(np.abs(ok[lag] - ok["first_value"]) / ok["first_value"])) if len(ok) else np.nan
    return pd.DataFrame([out])

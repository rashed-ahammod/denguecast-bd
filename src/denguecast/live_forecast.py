"""Build and publish a weekly live forecast.

``build_forecast(as_of, model)`` is pure: it reads data only through
archive.get_data(as_of=...) and never looks at the clock, so the leakage test
(L10) can re-run it on an archive truncated at as_of and compare outputs.

CLI (run by .github/workflows/forecast.yml every Saturday 22:30 BDT):
    python -m denguecast.live_forecast --model persistence
It refuses to overwrite an existing forecast for the same origin and model,
and marks a forecast "late" if it is created after Sunday 12:00 BDT.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from . import archive, baselines, cleaning, config

BDT = "Asia/Dhaka"


def weekly_series(as_of, archive_file: Path | None = None, log: cleaning.QualityLog | None = None,
                  include_test_seasons: bool = False) -> pd.DataFrame:
    """Weekly admissions per unit as known at as_of: unit, week_end, value, value_clipped.
    Uses published epi-week rows where present, otherwise aggregates daily rows."""
    log = log or cleaning.QualityLog()
    kw = dict(archive_file=archive_file, include_test_seasons=include_test_seasons)
    ep = archive.get_data(as_of=as_of, metrics=["admissions"], period="epiweek", **kw)
    day = archive.get_data(as_of=as_of, metrics=["admissions"], period="day", **kw)
    cum = archive.get_data(as_of=as_of, metrics=["cumulative_admissions"], period="day", **kw)
    parts = []
    if not day.empty:
        wk = cleaning.daily_to_weekly(day[["unit", "reference_date", "value"]], log, cumulative=cum)
        parts.append(wk.assign(source_kind="daily"))
    if not ep.empty:
        e = ep.rename(columns={"reference_date": "week_end"})[["unit", "week_end", "value"]].copy()
        e["week_end"] = pd.to_datetime(e["week_end"]).dt.date
        e = cleaning.add_epiweek_columns(e.assign(reference_date=e["week_end"])).drop(columns=["reference_date"])
        e["flag"] = ""
        parts.append(e[cleaning.WEEKLY_COLS].assign(source_kind="epiweek"))
    if not parts:
        return pd.DataFrame(columns=cleaning.WEEKLY_COLS + ["value_clipped"])
    allw = pd.concat(parts, ignore_index=True)
    # Prefer published epi-week values over aggregated daily values for the same week.
    allw["_rank"] = allw["source_kind"].map({"epiweek": 0, "daily": 1})
    allw = allw.sort_values("_rank").drop_duplicates(["unit", "week_end"]).drop(columns=["_rank", "source_kind"])
    allw = cleaning.merge_city_corporations_if_incomplete(allw, log)
    allw = cleaning.add_dhaka_div_total(allw, log)
    allw = cleaning.flag_outliers(allw, log)
    return allw


def latest_complete_origin(weekly: pd.DataFrame, as_of) -> pd.Timestamp | None:
    """Origin W = latest epi week (ending on or before as_of) with an observed national value."""
    t = archive.to_utc(as_of).tz_convert(BDT).date()
    nat = weekly[(weekly["unit"] == "NATIONAL") & weekly["value"].notna()]
    nat = nat[pd.to_datetime(nat["week_end"]).dt.date <= t]
    return pd.Timestamp(nat["week_end"].max()) if not nat.empty else None


def build_forecast(as_of, model: str = "persistence", archive_file: Path | None = None) -> tuple[pd.DataFrame, dict]:
    log = cleaning.QualityLog()
    weekly = weekly_series(as_of, archive_file=archive_file, log=log)
    origin = latest_complete_origin(weekly, as_of)
    if origin is None:
        raise baselines.InsufficientHistory("no complete epi week with a national value is available")
    history = weekly[["unit", "week_end", "value_clipped"]].rename(columns={"value_clipped": "value"})
    if model == "persistence":
        fc = baselines.persistence(history, origin, on_missing="skip")
    elif model == "seasonal_naive":
        fc = baselines.seasonal_naive(history, origin)
    else:
        raise ValueError(f"unknown model {model!r}")
    meta = {
        "model": model,
        "as_of_utc": archive.to_utc(as_of).isoformat(),
        "origin_week_end": str(origin.date()),
        "units_forecast": sorted(fc["unit"].unique().tolist()),
        "units_skipped": fc.attrs.get("skipped_units", []),
        "interval_basis": fc.groupby("unit")["interval_basis"].first().to_dict(),
        "weeks_of_history": int(weekly["week_end"].nunique()),
        "quality_log_entries": len(log.entries),
    }
    return fc, meta


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=config.REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="persistence", choices=["persistence", "seasonal_naive"])
    ap.add_argument("--as-of", default=None, help="UTC timestamp; default now (live use)")
    args = ap.parse_args(argv)
    now = archive.utc_now()
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp(now)
    try:
        fc, meta = build_forecast(as_of, args.model)
    except baselines.InsufficientHistory as exc:
        print(f"NOT PUBLISHED: insufficient data: {exc}", file=sys.stderr)
        return 2
    origin = pd.Timestamp(meta["origin_week_end"])
    out_dir = config.FORECAST_DIR / meta["origin_week_end"]
    csv_path, meta_path = out_dir / f"{args.model}.csv", out_dir / f"{args.model}.json"
    if csv_path.exists():
        print(f"NOT PUBLISHED: {csv_path} already exists; forecasts are never overwritten.", file=sys.stderr)
        return 3
    # Commit deadline: Sunday 12:00 BDT after the origin Saturday.
    deadline = (origin + pd.Timedelta(days=1, hours=12)).tz_localize(BDT)
    created = pd.Timestamp(now).tz_convert(BDT)
    meta.update(created_at_bdt=created.isoformat(), commit_deadline_bdt=deadline.isoformat(),
                late=bool(created > deadline), code_commit=_git_sha())
    out_dir.mkdir(parents=True, exist_ok=True)
    fc.to_csv(csv_path, index=False)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Published {csv_path} (origin {meta['origin_week_end']}, late={meta['late']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

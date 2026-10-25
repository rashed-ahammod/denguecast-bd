"""Ingest hand-transcribed DGHS daily releases into the archive.

This is the fallback data path while the dashboard parser is blocked (B2).
File: data/manual/daily_releases.csv, one row per (report_date, unit):
    report_date, unit, admissions, stated_total, source_url, entered_by, note
Rules:
- Every row needs a source_url pointing at the official release or a reprint.
- For each report_date, the subnational units must sum exactly to stated_total;
  if not, that date is rejected and reported (nothing is "fixed").
- A NATIONAL row is added from stated_total.
- Optional column ``release_complete``: "no" marks a release whose area figures
  are contradictory or incomplete in every available source (deviation log,
  2026-10-25). For such a date only the areas listed (those all sources agree
  on) and the stated total are stored; the listed areas must not exceed the
  total, and a week containing that date is missing for every unlisted area.
- Rows already in the archive are skipped (idempotent).
Usage:  python -m denguecast.ingest_manual
"""
from __future__ import annotations

import sys

import pandas as pd

from . import archive, config

MANUAL_FILE = config.MANUAL_DIR / "daily_releases.csv"
REQUIRED = ["report_date", "unit", "admissions", "stated_total", "source_url", "entered_by"]


def build_rows(manual: pd.DataFrame, retrieved_at) -> tuple[pd.DataFrame, list[str]]:
    problems: list[str] = []
    missing = [c for c in REQUIRED if c not in manual.columns]
    if missing:
        raise ValueError(f"manual file missing columns: {missing}")
    if manual["source_url"].fillna("").str.strip().eq("").any():
        problems.append("rows without source_url were rejected")
        manual = manual[manual["source_url"].fillna("").str.strip() != ""]
    out = []
    for d, g in manual.groupby("report_date"):
        totals = g["stated_total"].dropna().unique()
        if len(totals) != 1:
            problems.append(f"{d}: stated_total missing or inconsistent across rows; date rejected")
            continue
        if g["unit"].duplicated().any():
            problems.append(f"{d}: duplicate units; date rejected")
            continue
        s = int(g["admissions"].sum())
        partial = "release_complete" in g.columns and str(g["release_complete"].iloc[0]).strip().lower() == "no"
        if partial and s > int(totals[0]):
            problems.append(f"{d}: listed areas sum to {s}, above the stated total {int(totals[0])}; date rejected")
            continue
        if not partial and s != int(totals[0]):
            problems.append(f"{d}: units sum to {s} but release states {int(totals[0])}; date rejected")
            continue
        avail = pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=config.ASSUMED_PUBLICATION_HOUR_UTC)
        base = dict(period="day", metric="admissions", source="dghs_press_release", vintage_type="first_reported",
                    available_at=avail.isoformat(), available_at_basis="assumed",
                    retrieved_at=pd.Timestamp(retrieved_at).isoformat(), raw_sha256="")
        url = g["source_url"].iloc[0]
        for r in g.itertuples():
            out.append({**base, "unit": r.unit, "reference_date": str(d), "value": int(r.admissions),
                        "source_url": r.source_url, "note": f"manual entry by {r.entered_by}"})
        out.append({**base, "unit": "NATIONAL", "reference_date": str(d), "value": int(totals[0]),
                    "source_url": url, "note": "national = stated_total of the release"
                    + ("; partial release: only areas agreed by all sources stored" if partial else "")})
    return pd.DataFrame(out), problems


def main() -> int:
    if not MANUAL_FILE.exists():
        print(f"No manual file at {MANUAL_FILE}; nothing to ingest.")
        return 0
    manual = pd.read_csv(MANUAL_FILE, dtype={"report_date": str})
    if manual.empty:
        print("Manual file is empty; nothing to ingest.")
        return 0
    rows, problems = build_rows(manual, archive.utc_now())
    for p in problems:
        print(f"REJECTED: {p}", file=sys.stderr)
    n = archive.append_observations(rows) if not rows.empty else 0
    print(f"Appended {n} rows from {MANUAL_FILE.name}; {len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

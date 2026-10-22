"""Epidemiological weeks as used by the DGHS dengue dashboard.

Weeks run Sunday to Saturday and are assigned by DGHS report date. Week 1 is
the first Sunday-Saturday week with at least four days in the new year (the
US CDC / MMWR rule). This was inferred from two dashboard observations
(12 Apr 2026 -> W15; 18-24 Oct 2026 -> W42) and is assumption A1 in
docs/ASSUMPTIONS_AND_BLOCKERS.md.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from epiweeks import Week


def epiweek_of(d: date) -> tuple[int, int]:
    """Return (epi_year, epi_week) for a report date."""
    w = Week.fromdate(d, system="cdc")
    return w.year, w.week


def week_start(epi_year: int, epi_week: int) -> date:
    return Week(epi_year, epi_week, system="cdc").startdate()


def week_end(epi_year: int, epi_week: int) -> date:
    return Week(epi_year, epi_week, system="cdc").enddate()


def week_end_of(d: date) -> date:
    """Saturday that closes the epi week containing d."""
    return Week.fromdate(d, system="cdc").enddate()


def shift_week_end(week_end_date: date, weeks: int) -> date:
    return week_end_date + timedelta(weeks=weeks)


def add_epiweek_columns(df: pd.DataFrame, date_col: str = "reference_date") -> pd.DataFrame:
    """Add epi_year, epi_week and week_end columns based on a date column."""
    out = df.copy()
    dates = pd.to_datetime(out[date_col]).dt.date
    weeks = [Week.fromdate(d, system="cdc") for d in dates]
    out["epi_year"] = [w.year for w in weeks]
    out["epi_week"] = [w.week for w in weeks]
    out["week_end"] = [w.enddate() for w in weeks]
    return out

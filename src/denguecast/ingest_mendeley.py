"""Ingest the Mendeley dataset z5mvwrfgsz v1 (Naher 2026, CC BY 4.0):
division-wise daily dengue admissions, 2022-2024, one CSV per division.

Files are read from the raw snapshots logged in data/archive/raw_manifest.csv
(source ``mendeley_z5mvwrfgsz_files``), so every archived row carries the
SHA-256 of the file it came from.

Structure (checked on 2022-2023 rows only, docs/ASSUMPTIONS_AND_BLOCKERS.md):
- ``Date`` as dd-mm-yy; one admissions column per file (see UNIT_MAP).
- ``Dhaka`` is the whole division including DNCC and DSCC -> DHAKA_DIV_TOTAL.
- No national series. A NATIONAL row is constructed as the sum of the 8
  division files for days where all 8 are valid (amendment D10), and each
  such row says so in its note.

Rows outside ``years`` (epi years) are dropped while reading, before anything
is counted or printed. Test seasons need config.ALLOW_TEST_ENV=1 (Step 9).

Usage:  python -m denguecast.ingest_mendeley [--years 2022 2023]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime

import pandas as pd

from . import archive, config
from .epiweek import epiweek_of

SOURCE = "mendeley_z5mvwrfgsz"
RAW_SOURCE = "mendeley_z5mvwrfgsz_files"
DATASET_URL = "https://data.mendeley.com/datasets/z5mvwrfgsz/1"
DEFAULT_YEARS = {2022, 2023}
# Admissions column header -> unit. Spellings exactly as in the files.
UNIT_MAP = {
    "effected-Barishal": "BARISHAL_DIV",
    "effected-chittagong": "CHATTOGRAM_DIV",
    "effected-khulna": "KHULNA_DIV",
    "effected-Mymensingh": "MYMENSINGH_DIV",
    "effected-Rajhshahi": "RAJSHAHI_DIV",
    "effected-Rangpur": "RANGPUR_DIV",
    "effected-Syllhet": "SYLHET_DIV",
}
# Dhaka.csv has columns Date, Division, effected, ... with Division == "Dhaka".
DIVISION_MAP = {"Dhaka": config.DHAKA_DIV_TOTAL}
N_DIVISIONS = 8
NATIONAL_NOTE = "constructed: sum of the 8 Mendeley division files (D10); no national series is published in this dataset"


class UnmappedName(ValueError):
    pass


def _raw_files(manifest_file=None) -> pd.DataFrame:
    m = pd.read_csv(manifest_file or config.RAW_MANIFEST_FILE, dtype=str, keep_default_na=False)
    m = m[(m["source"] == RAW_SOURCE) & m["path"].str.lower().str.endswith(".csv")]
    # One row per distinct file content (the probe may log the same file twice).
    return m.drop_duplicates("sha256", keep="first")


def _parse_date(s: str):
    return datetime.strptime(s.strip(), "%d-%m-%y").date()


def read_file(path, years: set[int]) -> tuple[str, list[tuple]]:
    """Return (unit, [(date, raw_value), ...]) keeping only dates in ``years``."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], rows[1:]
    if "Division" in header:
        di, vi = header.index("Division"), header.index("effected")
        names = {r[di] for r in body if r}
        unknown = names - set(DIVISION_MAP)
        if unknown or len(names) != 1:
            raise UnmappedName(f"{path}: Division values {sorted(names)} not in {sorted(DIVISION_MAP)}")
        unit = DIVISION_MAP[names.pop()]
    else:
        cols = [c for c in header if c.startswith("effected")]
        if len(cols) != 1 or cols[0] not in UNIT_MAP:
            raise UnmappedName(f"{path}: admissions column {cols} not in mapping table")
        unit, vi = UNIT_MAP[cols[0]], header.index(cols[0])
    out = []
    for r in body:
        if not r:
            continue
        d = _parse_date(r[0])
        if epiweek_of(d)[0] not in years:  # filter before anything is counted
            continue
        out.append((d, r[vi].strip()))
    return unit, out


def _as_int(v: str):
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f >= 0 and f.is_integer() else None


def build_rows(years: set[int], manifest_file=None) -> tuple[pd.DataFrame, dict]:
    if years & config.TEST_SEASONS and not config.test_seasons_unlocked():
        raise archive.SeasonLockError(f"years {sorted(years & config.TEST_SEASONS)} are locked test seasons")
    files = _raw_files(manifest_file)
    rows, per_unit, per_day = [], {}, defaultdict(dict)
    for f in files.itertuples():
        path = config.REPO_ROOT / f.path.replace("\\", "/")  # early manifest rows used Windows separators
        unit, recs = read_file(path, years)
        if unit in per_unit:
            raise ValueError(f"two files map to {unit}")
        per_unit[unit] = recs
        for d, v in recs:
            per_day[d][unit] = _as_int(v)
            rows.append(dict(unit=unit, reference_date=d.isoformat(), value=v, source_url=f.url,
                             retrieved_at=f.retrieved_at, raw_sha256=f.sha256, note=""))
    if len(per_unit) != N_DIVISIONS:
        raise ValueError(f"expected {N_DIVISIONS} division files, found {sorted(per_unit)}")
    for d, vals in sorted(per_day.items()):
        complete = len(vals) == N_DIVISIONS and all(v is not None for v in vals.values())
        rows.append(dict(unit="NATIONAL", reference_date=d.isoformat(),
                         value=sum(vals.values()) if complete else "", source_url=DATASET_URL,
                         retrieved_at=files["retrieved_at"].max(), raw_sha256="",
                         note=NATIONAL_NOTE if complete else NATIONAL_NOTE + "; not constructed: a division is missing or invalid"))
    df = pd.DataFrame(rows)
    df["period"], df["metric"], df["source"], df["vintage_type"] = "day", "admissions", SOURCE, "final"
    df["available_at"] = [(pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=config.ASSUMED_PUBLICATION_HOUR_UTC)).isoformat()
                          for d in df["reference_date"]]
    df["available_at_basis"] = "assumed"
    report = _report(per_unit, per_day)
    return df[archive.COLUMNS], report


def _report(per_unit: dict, per_day: dict) -> dict:
    rep = {"units": {}, "dncc_dscc_separate": any(u in per_unit for u in ("DNCC", "DSCC")),
           "national_series_in_source": "NATIONAL" in per_unit}
    for unit, recs in sorted(per_unit.items()):
        days = sorted(d for d, _ in recs)
        span = (days[-1] - days[0]).days + 1 if days else 0
        invalid = sum(_as_int(v) is None for _, v in recs)
        rep["units"][unit] = dict(days=len(days), first=str(days[0]) if days else "", last=str(days[-1]) if days else "",
                                  missing_days=span - len(set(days)), invalid_values=invalid)
    rep["national_days_constructed"] = sum(
        len(v) == N_DIVISIONS and all(x is not None for x in v.values()) for v in per_day.values())
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+", default=sorted(DEFAULT_YEARS), help="epi years to ingest")
    args = ap.parse_args(argv)
    rows, rep = build_rows(set(args.years))
    n = archive.append_observations(rows)
    print(f"Mendeley z5mvwrfgsz, epi years {args.years}: appended {n} rows ({len(rows)} built).")
    print(f"DNCC/DSCC separate: {rep['dncc_dscc_separate']}; national series in source: {rep['national_series_in_source']}; "
          f"NATIONAL constructed for {rep['national_days_constructed']} days (D10).")
    for unit, r in rep["units"].items():
        print(f"  {unit:16s} days={r['days']} {r['first']}..{r['last']} missing_days={r['missing_days']} invalid={r['invalid_values']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

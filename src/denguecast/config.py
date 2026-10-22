"""Central configuration for DengueCast BD.

Every value here mirrors the pre-registration document. Changing any of them
after the pre-registration is locked must be recorded in docs/DEVIATIONS.md.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
RAW_DIR = DATA_DIR / "raw"
MANUAL_DIR = DATA_DIR / "manual"
FORECAST_DIR = REPO_ROOT / "forecasts"

# The only file that stores observations. Only archive.py may read or write it.
OBSERVATIONS_FILE = ARCHIVE_DIR / "observations.csv"
RAW_MANIFEST_FILE = ARCHIVE_DIR / "raw_manifest.csv"
QUALITY_LOG_FILE = DATA_DIR / "quality_log.csv"

# Reporting units (pre-registration Section 3). Codes are stable identifiers.
UNITS = [
    "NATIONAL",
    "DHAKA_DIV",  # Dhaka division outside DNCC and DSCC
    "CHATTOGRAM_DIV",
    "BARISHAL_DIV",
    "KHULNA_DIV",
    "RAJSHAHI_DIV",
    "RANGPUR_DIV",
    "MYMENSINGH_DIV",
    "SYLHET_DIV",
    "DNCC",
    "DSCC",
]
SUBNATIONAL_UNITS = [u for u in UNITS if u != "NATIONAL"]
# Coarser unit used by cleaning rule 8 when DNCC and DSCC are not reported separately.
MERGED_DHAKA_CITY = "DHAKA_CITY"

METRICS = ("admissions", "currently_admitted", "deaths", "cumulative_admissions")

# Seasons (pre-registration Section 8, as filled on 2026-10-23).
TRAIN_SEASONS = {2022}
VALIDATION_SEASONS = {2023}
DEV_SEASONS = TRAIN_SEASONS | VALIDATION_SEASONS
TEST_SEASONS = {2024, 2025}  # locked: never loaded unless explicitly unlocked
LIVE_SEASON = 2026

# Test seasons are unlocked only when this environment variable is "1".
# It must only be set by the final, post-lock evaluation run.
ALLOW_TEST_ENV = "DENGUECAST_ALLOW_TEST_SEASONS"


def test_seasons_unlocked() -> bool:
    return os.environ.get(ALLOW_TEST_ENV) == "1"


# Forecast format (pre-registration Section 3).
QUANTILES = [0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975]
HORIZONS = [1, 2, 3, 4]
# Central interval levels used in WIS: alpha = 0.05, 0.10, 0.20, 0.50
ALPHAS = [0.05, 0.10, 0.20, 0.50]

RANDOM_SEED = 2026

# Assumed availability time for historical rows whose publication time is
# unknown: 18:00 Bangladesh time (12:00 UTC) on the report date. See
# docs/ASSUMPTIONS_AND_BLOCKERS.md, assumption A4.
ASSUMED_PUBLICATION_HOUR_UTC = 12

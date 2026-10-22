"""Shared fixtures. All series built here are SYNTHETIC and exist only to test
code mechanics; they are never written to the real archive."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from denguecast import config


def synthetic_daily_rows(start: date, end: date, units=None, seed: int = 0,
                         available_lag_hours: int = 12, vintage: str = "final") -> pd.DataFrame:
    """SYNTHETIC daily admissions with a seasonal shape, as archive rows."""
    rng = np.random.default_rng(seed)
    units = units or ["NATIONAL", "DHAKA_DIV", "BARISHAL_DIV", "DNCC", "DSCC"]
    rows = []
    d = start
    while d <= end:
        season = 5 + 200 * np.exp(-((d.timetuple().tm_yday - 260) / 40) ** 2)
        for i, u in enumerate(units):
            lam = season * (3 if u == "NATIONAL" else 1 / (i + 1))
            avail = pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=available_lag_hours)
            rows.append(dict(
                unit=u, reference_date=d.isoformat(), period="day", metric="admissions",
                value=int(rng.poisson(lam)), source="synthetic_test", source_url="",
                vintage_type=vintage, available_at=avail.isoformat(), available_at_basis="assumed",
                retrieved_at=avail.isoformat(), raw_sha256="", note="SYNTHETIC TEST DATA",
            ))
        d += timedelta(days=1)
    return pd.DataFrame(rows)


@pytest.fixture
def tmp_archive(tmp_path, monkeypatch):
    """Point every archive path at a temporary directory."""
    monkeypatch.setattr(config, "OBSERVATIONS_FILE", tmp_path / "archive" / "observations.csv")
    monkeypatch.setattr(config, "RAW_MANIFEST_FILE", tmp_path / "archive" / "raw_manifest.csv")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "QUALITY_LOG_FILE", tmp_path / "quality_log.csv")
    monkeypatch.delenv(config.ALLOW_TEST_ENV, raising=False)
    return tmp_path / "archive" / "observations.csv"

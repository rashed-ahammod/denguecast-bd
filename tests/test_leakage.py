"""Leakage test L10 (pre-registration Section 6).

A forecast made at origin time t from the full archive must be identical to
one made from an archive truncated to rows available at or before t. The
archive used here is SYNTHETIC and deliberately contains later revisions and
future rows that would change the forecast if they leaked."""
from datetime import date

import pandas as pd
import pytest

from denguecast import archive, live_forecast
from conftest import synthetic_daily_rows


@pytest.fixture
def leaky_archive(tmp_archive):
    rows = synthetic_daily_rows(date(2022, 1, 1), date(2023, 12, 30), seed=3)
    archive.append_observations(rows)
    # Later revisions of past days (available 30 days later, values doubled)
    rev = rows.copy()
    rev["value"] = rev["value"] * 2
    later = pd.to_datetime(rev["available_at"]) + pd.Timedelta(days=30)
    rev["available_at"] = later.map(lambda t: t.isoformat())
    rev["retrieved_at"] = rev["available_at"]
    rev["vintage_type"] = "live"
    rev["raw_sha256"] = "revision"
    archive.append_observations(rev)
    return tmp_archive


@pytest.mark.parametrize("as_of", [
    "2022-08-14T00:00:00+00:00",
    "2023-03-05T06:00:00+00:00",
    "2023-09-17T13:00:00+00:00",
    "2023-12-02T23:00:00+00:00",
])
def test_full_vs_truncated_archive_identical(leaky_archive, tmp_path, as_of):
    truncated = tmp_path / "truncated.csv"
    archive.write_truncated_archive(as_of, leaky_archive, truncated)
    fc_full, meta_full = live_forecast.build_forecast(as_of, "persistence", archive_file=leaky_archive)
    fc_trunc, meta_trunc = live_forecast.build_forecast(as_of, "persistence", archive_file=truncated)
    pd.testing.assert_frame_equal(fc_full, fc_trunc)
    assert meta_full["origin_week_end"] == meta_trunc["origin_week_end"]


def test_revisions_are_used_only_after_they_exist(leaky_archive):
    early = archive.get_data("2023-06-10T00:00:00+00:00", period="day", archive_file=leaky_archive)
    # A day 10 days before as_of: its revision (30-day lag) is not yet available
    v = early[(early.unit == "NATIONAL") & (early.reference_date == "2023-05-31")]["value"].iloc[0]
    late = archive.get_data("2023-08-10T00:00:00+00:00", period="day", archive_file=leaky_archive)
    v2 = late[(late.unit == "NATIONAL") & (late.reference_date == "2023-05-31")]["value"].iloc[0]
    assert v2 == 2 * v


def test_live_ensemble_full_vs_truncated_archive_identical(leaky_archive, tmp_path):
    as_of = "2023-09-17T13:00:00+00:00"
    truncated = tmp_path / "truncated.csv"
    archive.write_truncated_archive(as_of, leaky_archive, truncated)
    fc_full, _ = live_forecast.build_forecast(as_of, "ensemble", archive_file=leaky_archive)
    fc_trunc, _ = live_forecast.build_forecast(as_of, "ensemble", archive_file=truncated)
    assert len(fc_full) > 0
    pd.testing.assert_frame_equal(fc_full, fc_trunc)

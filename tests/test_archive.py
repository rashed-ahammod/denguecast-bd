from datetime import date

import pandas as pd
import pytest

from denguecast import archive, config
from conftest import synthetic_daily_rows


def _row(**kw):
    base = dict(unit="DNCC", reference_date="2023-08-01", period="day", metric="admissions", value=10,
                source="synthetic_test", source_url="", vintage_type="live",
                available_at="2023-08-01T12:00:00+00:00", available_at_basis="retrieved",
                retrieved_at="2023-08-01T12:00:00+00:00", raw_sha256="a", note="SYNTHETIC")
    base.update(kw)
    return pd.DataFrame([base])


def test_append_only_and_idempotent(tmp_archive):
    assert archive.append_observations(_row()) == 1
    before = tmp_archive.read_text()
    assert archive.append_observations(_row()) == 0  # exact duplicate skipped
    archive.append_observations(_row(value=12, raw_sha256="b", available_at="2023-08-03T12:00:00+00:00",
                                     retrieved_at="2023-08-03T12:00:00+00:00"))
    after = tmp_archive.read_text()
    assert after.startswith(before)  # nothing earlier was changed


def test_as_of_returns_version_known_then(tmp_archive):
    archive.append_observations(_row())
    archive.append_observations(_row(value=12, raw_sha256="b", available_at="2023-08-03T12:00:00+00:00",
                                     retrieved_at="2023-08-03T12:00:00+00:00"))
    early = archive.get_data("2023-08-02T00:00:00+00:00")
    late = archive.get_data("2023-08-04T00:00:00+00:00")
    before_any = archive.get_data("2023-08-01T11:59:59+00:00")
    assert early["value"].tolist() == [10]
    assert late["value"].tolist() == [12]
    assert before_any.empty


def test_naive_timestamps_rejected(tmp_archive):
    with pytest.raises(ValueError):
        archive.get_data("2023-08-02T00:00:00")
    with pytest.raises(ValueError):
        archive.append_observations(_row(available_at="2023-08-01T12:00:00"))


def test_invalid_value_stored_empty_and_noted(tmp_archive):
    archive.append_observations(_row(value="12a"))
    df = archive.get_data("2024-01-01T00:00:00+00:00")
    assert df["value"].isna().all()
    assert "invalid published value" in pd.read_csv(tmp_archive)["note"].iloc[0]


def test_unknown_unit_rejected(tmp_archive):
    with pytest.raises(ValueError):
        archive.append_observations(_row(unit="DHAKA"))


def test_test_seasons_locked(tmp_archive, monkeypatch):
    rows = synthetic_daily_rows(date(2023, 12, 25), date(2024, 1, 10), units=["NATIONAL"])
    archive.append_observations(rows)
    df = archive.get_data("2026-01-01T00:00:00+00:00")
    seasons = {archive._season_of(d) for d in df["reference_date"]}
    assert 2024 not in seasons and 2023 in seasons
    with pytest.raises(archive.SeasonLockError):
        archive.get_data("2026-01-01T00:00:00+00:00", include_test_seasons=True)
    monkeypatch.setenv(config.ALLOW_TEST_ENV, "1")
    df2 = archive.get_data("2026-01-01T00:00:00+00:00", include_test_seasons=True)
    assert 2024 in {archive._season_of(d) for d in df2["reference_date"]}


def test_raw_snapshot_hash_and_dedup(tmp_archive):
    d1, p1 = archive.save_raw_snapshot(b"<html>x</html>", "src", "http://x", "html")
    d2, p2 = archive.save_raw_snapshot(b"<html>x</html>", "src", "http://x", "html")
    assert d1 == d2 and p1 == p2
    manifest = pd.read_csv(config.RAW_MANIFEST_FILE)
    assert len(manifest) == 2 and manifest["duplicate_of_existing"].tolist() == [False, True]

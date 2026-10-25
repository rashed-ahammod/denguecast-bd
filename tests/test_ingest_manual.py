import pandas as pd

from denguecast import archive
from denguecast.ingest_manual import build_rows


def _manual(rows):
    return pd.DataFrame(rows, columns=["report_date", "unit", "admissions", "stated_total", "source_url", "entered_by"])


def test_consistent_release_ingested_with_national(tmp_archive):
    m = _manual([["2026-01-12", "BARISHAL_DIV", 7, 10, "http://src", "t"],
                 ["2026-01-12", "DNCC", 3, 10, "http://src", "t"]])
    rows, problems = build_rows(m, "2026-01-12T15:00:00+00:00")
    assert not problems
    assert set(rows["unit"]) == {"BARISHAL_DIV", "DNCC", "NATIONAL"}
    assert archive.append_observations(rows) == 3


def test_sum_mismatch_rejected_not_fixed():
    m = _manual([["2026-08-15", "BARISHAL_DIV", 17, 730, "http://src", "t"],
                 ["2026-08-15", "DNCC", 171, 730, "http://src", "t"]])
    rows, problems = build_rows(m, "2026-08-15T15:00:00+00:00")
    assert rows.empty and "units sum to 188" in problems[0]


def test_missing_source_rejected():
    m = _manual([["2026-01-12", "DNCC", 10, 10, "", "t"]])
    rows, problems = build_rows(m, "2026-01-12T15:00:00+00:00")
    assert rows.empty and problems


def test_partial_release_keeps_listed_areas_and_total():
    m = _manual([["2026-10-20", "BARISHAL_DIV", 191, 1366, "http://src", "t"],
                 ["2026-10-20", "KHULNA_DIV", 141, 1366, "http://src", "t"]]).assign(release_complete="no")
    rows, problems = build_rows(m, "2026-10-25T00:00:00+00:00")
    assert not problems
    assert set(rows["unit"]) == {"BARISHAL_DIV", "KHULNA_DIV", "NATIONAL"}
    assert rows.loc[rows["unit"] == "NATIONAL", "value"].iloc[0] == 1366


def test_partial_release_cannot_exceed_total():
    m = _manual([["2026-10-20", "BARISHAL_DIV", 1000, 1366, "http://src", "t"],
                 ["2026-10-20", "KHULNA_DIV", 400, 1366, "http://src", "t"]]).assign(release_complete="no")
    rows, problems = build_rows(m, "2026-10-25T00:00:00+00:00")
    assert rows.empty and "above the stated total" in problems[0]


def test_complete_is_default_and_still_exact():
    m = _manual([["2026-10-20", "BARISHAL_DIV", 191, 1366, "http://src", "t"]]).assign(release_complete="yes")
    rows, problems = build_rows(m, "2026-10-25T00:00:00+00:00")
    assert rows.empty and "units sum to 191" in problems[0]

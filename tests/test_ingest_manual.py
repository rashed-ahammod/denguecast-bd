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

"""ingest_mendeley on SYNTHETIC files with the real headers and date format."""
import csv
from datetime import date, timedelta

import pandas as pd
import pytest

from denguecast import archive, cleaning, config, ingest_mendeley

HEADERS = {
    "Barisal.csv": ["Date", "effected-Barishal", "Rainfall"],
    "Chittagong.csv": ["Date", "effected-chittagong", "Rainfall"],
    "Dhaka.csv": ["Date", "Division", "effected", "Rainfall"],
    "khulna.csv": ["Date", "effected-khulna", "Rainfall"],
    "Mymensingh.csv": ["Date", "effected-Mymensingh", "Rainfall"],
    "Rajshahi.csv": ["Date", "effected-Rajhshahi", "Rainfall"],
    "Rangpur.csv": ["Date", "effected-Rangpur", "Rainfall"],
    "Sylhet.csv": ["Date", "effected-Syllhet", "Rainfall"],
}


@pytest.fixture
def mendeley_files(tmp_archive, tmp_path, monkeypatch):
    """SYNTHETIC: 2023-12-24..2024-01-13 (crosses into epi year 2024), value 2.0 per day."""
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    days = [date(2023, 12, 24) + timedelta(days=i) for i in range(21)]
    for name, header in HEADERS.items():
        rows = [header]
        for d in days:
            ds = d.strftime("%d-%m-%y")
            rows.append([ds, "Dhaka", "2.0", "0"] if "Division" in header else [ds, "2.0", "0"])
        p = tmp_path / name
        with p.open("w", newline="") as fh:
            csv.writer(fh).writerows(rows)
        archive.save_raw_snapshot(p.read_bytes(), ingest_mendeley.RAW_SOURCE, f"https://example/{name}", "csv")
    return tmp_archive


def test_filters_years_while_reading_and_constructs_national(mendeley_files):
    rows, rep = ingest_mendeley.build_rows({2023})
    assert set(rows["reference_date"]) == {str(date(2023, 12, 24) + timedelta(days=i)) for i in range(7)}
    assert rows["reference_date"].max() == "2023-12-30"  # 31 Dec 2023 is epi year 2024
    nat = rows[rows["unit"] == "NATIONAL"]
    assert (nat["value"] == 16).all() and nat["note"].str.contains("constructed").all()
    assert set(rows["unit"]) == {"NATIONAL", "DHAKA_DIV_TOTAL", "BARISHAL_DIV", "CHATTOGRAM_DIV", "KHULNA_DIV",
                                 "MYMENSINGH_DIV", "RAJSHAHI_DIV", "RANGPUR_DIV", "SYLHET_DIV"}
    assert not rep["dncc_dscc_separate"] and not rep["national_series_in_source"]
    assert archive.append_observations(rows) == 63  # 9 units x 7 days
    assert archive.append_observations(rows) == 0  # idempotent


def test_test_season_years_are_locked(mendeley_files):
    with pytest.raises(archive.SeasonLockError):
        ingest_mendeley.build_rows({2024})


def test_unmapped_name_stops(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Date,effected-Unknown\n01-01-23,1\n")
    with pytest.raises(ingest_mendeley.UnmappedName):
        ingest_mendeley.read_file(p, {2023})


def test_truth_from_seven_daily_values(mendeley_files):
    rows, _ = ingest_mendeley.build_rows({2023})
    archive.append_observations(rows)
    t = cleaning.final_truth_table(["NATIONAL", "SYLHET_DIV"], [date(2023, 12, 30)], "admissions",
                                   "2024-03-01T00:00:00+00:00")
    assert t["value"].tolist() == [112.0, 14.0]
    assert (t["truth_source"] == "mendeley_z5mvwrfgsz (7 daily)").all() and not t["provisional"].any()


def test_dhaka_div_total_derived_only_when_complete():
    log = cleaning.QualityLog()
    wk = pd.DataFrame({"unit": ["DHAKA_DIV", "DNCC", "DSCC", "DHAKA_DIV", "DNCC"], "epi_year": 2026, "epi_week": [42] * 3 + [43] * 2,
                       "week_end": [date(2026, 10, 24)] * 3 + [date(2026, 10, 31)] * 2,
                       "value": [10.0, 20.0, 30.0, 1.0, 2.0], "flag": ""})
    out = cleaning.add_dhaka_div_total(wk, log)
    tot = out[out["unit"] == "DHAKA_DIV_TOTAL"].set_index("week_end")["value"]
    assert tot[date(2026, 10, 24)] == 60.0 and pd.isna(tot[date(2026, 10, 31)])

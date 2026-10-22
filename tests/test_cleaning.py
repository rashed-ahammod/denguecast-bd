from datetime import date, timedelta

import numpy as np
import pandas as pd

from denguecast import cleaning


def _daily(values, start=date(2023, 1, 1), unit="DNCC"):
    return pd.DataFrame({"unit": unit, "reference_date": [start + timedelta(days=i) for i in range(len(values))],
                         "value": values})


def test_full_weeks_sum_and_partial_weeks_missing():
    log = cleaning.QualityLog()
    # 2023-01-01 is a Sunday; 10 days = one full week + 3 days of the next
    wk = cleaning.daily_to_weekly(_daily([1] * 10), log)
    assert wk["value"].iloc[0] == 7
    assert np.isnan(wk["value"].iloc[1]) and wk["flag"].iloc[1] == "missing"


def test_gap_recovered_from_cumulative():
    log = cleaning.QualityLog()
    vals = [2, 2, np.nan, np.nan, 2, 2, 2]
    cum = pd.DataFrame({"unit": "DNCC", "reference_date": [str(date(2023, 1, 2)), str(date(2023, 1, 5))],
                        "value": [4, 12]})  # 12 - 4 - 2 (day after gap) = 6 over the 2 missing days
    wk = cleaning.daily_to_weekly(_daily(vals), log, cumulative=cum)
    assert wk["value"].iloc[0] == 2 + 2 + 6 + 2 + 2 + 2
    assert wk["flag"].iloc[0] == "recovered"
    assert any(e["rule"] == "3" for e in log.entries)


def test_gap_without_cumulative_left_missing():
    log = cleaning.QualityLog()
    wk = cleaning.daily_to_weekly(_daily([2, 2, np.nan, 2, 2, 2, 2]), log)
    assert np.isnan(wk["value"].iloc[0])
    assert any(e["rule"] == "4" for e in log.entries)


def test_consistency_flag():
    log = cleaning.QualityLog()
    wk = pd.DataFrame({"unit": ["NATIONAL", "DNCC", "DSCC"], "week_end": [date(2023, 1, 7)] * 3,
                       "value": [100.0, 50.0, 40.0]})
    flagged = cleaning.consistency_check(wk, log)
    assert len(flagged) == 1 and np.isclose(flagged["rel_diff"].iloc[0], 0.10)


def test_merge_city_corporations_when_one_missing():
    log = cleaning.QualityLog()
    wk = pd.DataFrame({"unit": ["DNCC", "DHAKA_DIV"], "epi_year": 2022, "epi_week": 1,
                       "week_end": [date(2022, 1, 8)] * 2, "value": [5.0, 3.0], "flag": ""})
    out = cleaning.merge_city_corporations_if_incomplete(wk, log)
    assert set(out["unit"]) == {"DHAKA_CITY", "DHAKA_DIV"}


def test_outlier_check_uses_past_only():
    log = cleaning.QualityLog()
    base = [10.0] * 12
    weeks = [date(2023, 1, 7) + timedelta(weeks=i) for i in range(13)]
    a = pd.DataFrame({"unit": "X", "week_end": weeks, "value": base + [10.0]})
    b = pd.DataFrame({"unit": "X", "week_end": weeks, "value": base + [500.0]})  # future spike
    fa, fb = cleaning.flag_outliers(a, log), cleaning.flag_outliers(b, log)
    # flags for the first 12 weeks must not depend on the 13th week
    assert fa["outlier"].iloc[:12].tolist() == fb["outlier"].iloc[:12].tolist()
    assert fb["outlier"].iloc[12] and fb["value"].iloc[12] == 500.0  # truth untouched
    assert fb["value_clipped"].iloc[12] < 500.0


def test_revision_summary():
    df = pd.DataFrame({"first_value": [100, 200], "value_1w": [110, 200], "value_2w": [110, 220], "value_4w": [110, 220]})
    s = cleaning.revision_summary(df)
    assert np.isclose(s["value_1w"].iloc[0], 0.05)

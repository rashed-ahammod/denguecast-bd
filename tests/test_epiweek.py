from datetime import date

from denguecast.epiweek import epiweek_of, week_end, week_end_of


def test_matches_dghs_dashboard_observations():
    # Assumption A1: DGHS showed W15 on Sunday 12 Apr 2026 and W42 on 20 Oct 2026.
    assert epiweek_of(date(2026, 4, 12)) == (2026, 15)
    assert epiweek_of(date(2026, 10, 20)) == (2026, 42)


def test_week_boundaries_sunday_to_saturday():
    assert week_end_of(date(2026, 10, 18)) == date(2026, 10, 24)  # Sunday -> Saturday
    assert week_end_of(date(2026, 10, 24)) == date(2026, 10, 24)
    assert week_end(2026, 50) == date(2026, 12, 19)
    assert week_end(2026, 51) == date(2026, 12, 26)


def test_year_boundary_follows_cdc_rule():
    # 1-3 Jan 2026 fall in 2025 week 53 under the CDC rule (to be re-checked against DGHS).
    assert epiweek_of(date(2026, 1, 3)) == (2025, 53)
    assert epiweek_of(date(2026, 1, 4)) == (2026, 1)

# Assumptions, verification status and blockers

Last updated: 2026-10-23. Every item states what was actually checked. "Unverified" means exactly that.

## Verified

| ID | What | How it was verified |
| --- | --- | --- |
| V1 | DGHS epi weeks match the CDC (MMWR) rule for 2026 | `epiweeks` gives W15 on Sun 12 Apr 2026 and W42 for 18-24 Oct 2026, matching two DGHS dashboard observations (12 Apr: W15 equal to that day's 13 cases; 20 Oct: W42 after three days of reports). |
| V2 | DGHS reporting areas: 8 divisions (Dhaka excluding the city corporations), DNCC, DSCC | DGHS daily releases reprinted by BSS, Observer and Ittefaq in August 2026. |
| V3 | Release parser reads real reprints correctly | 6 real 2026 reprints in `tests/fixtures/`; all parsed as hand-checked. 2 of the 6 are incomplete (areas sum to 640 vs 730 and 701 vs 702); the parser flags both. |
| V4 | Leakage test L10 detects leaks | A deliberately injected leak (ignoring `as_of`) made all 4 leakage cases and 2 related tests fail; restored code passes. |
| V5 | Test suite | 49 tests pass locally (Python 3.12). Model tests use synthetic data and verify mechanics only. |

## Assumptions (to confirm or record in the pre-registration before lock)

| ID | Assumption | Why | Risk |
| --- | --- | --- | --- |
| A1 | Epi weeks follow the CDC rule, including at the year boundary (1-3 Jan 2026 = 2025 W53) | Only mid-year weeks were observable | Wrong week numbers near New Year; re-check in January |
| A2 | Dashboard headline "W<n>: <value>" is week-to-date national admissions | Inferred from two snapshots | Not used anywhere until the raw HTML confirms it |
| A3 | A bare "Dhaka" in a reprint means Dhaka division outside the city corporations | Releases list DNCC and DSCC separately | Parser warns every time it applies this |
| A4 | Where publication time is unknown, a historical value counts as available at 18:00 BDT on its report date | DGHS releases appear in the afternoon or evening | Slight optimism if a release appeared later |
| A5 | Baseline intervals are re-centred so the median equals the point forecast; pooled across units if a unit has fewer than 20 ratios | Pre-registration says "intervals from the empirical distribution" without these details | Add to pre-registration Section 7 before lock |
| A6 | "Final truth" = the weekly value as known 14 days after the week ends | Pre-registration says "retrieved at least 14 days after"; this is the as-of reading of that rule | Add wording to Section 5 rule 5 before lock |
| A7 | Outlier rule floors the MAD at 1 | Otherwise every change in a flat low-count series is an "outlier" | Add to Section 5 rule 9 before lock |
| A8 | Weeks with fewer than 7 reported days are missing, not partial sums | Rule 4; avoids treating an incomplete week as low | None expected |
| A9 | Live forecasts use 2022-2023 and 2026 history only; 2024-2025 stay locked | Keeps test seasons untouched before the final evaluation | Fewer history weeks for live intervals |

## Proposed pre-registration changes (need your approval before lock)

- **P1:** add A5, A6 and A7 wording to the pre-registration.
- **P2:** Model A runs without weather and population features until those are ingested; record which forecasts used them.
- **P3:** B3 cannot be a 52-week seasonal ARIMA with only the 2022 training season. Proposed: ARIMA(1,1,1) on log(1+y) with two Fourier harmonics for the annual cycle, switching to SARIMA(1,1,1)(1,0,0,52) once at least 3 seasons are in the training data. Implemented this way in `models.py`, pending approval.

## Blockers

| ID | Blocker | What unblocks it | Status |
| --- | --- | --- | --- |
| B1 | The development sandbox cannot reach DGHS, Mendeley or Open-Meteo, so the Mendeley 2022-2024 dataset (daily? DNCC/DSCC separate? gaps? licence?) is **unverified** | Run the `probe` workflow on GitHub (open internet); it downloads and reports | Waiting for repository |
| B2 | DGHS dashboard raw HTML has never been inspected, so no division-table parser exists; the scraper stores raw pages only | Probe report shows how the dashboard delivers its tables | Waiting for B1 |
| B3 | Creating and pushing the public repository needs the team's GitHub account | Team creates the repo and pushes this code | Waiting for team |
| B4 | The first live forecast (Sat 24 Oct, origin W42) needs W42 values for every unit plus at least 20 weekly log ratios of history | Either B2 resolved, or the 7 daily releases for 18-24 Oct transcribed into `data/manual/daily_releases.csv` with sources, plus enough earlier weeks | Open |
| B5 | Weather (Open-Meteo) and population (census 2022) are not ingested | After B1 confirms Open-Meteo access | Open |
| B6 | Model A and B3 are untrained on real data; hyperparameters untuned | After Mendeley 2022-2023 ingestion (B1) | Open |

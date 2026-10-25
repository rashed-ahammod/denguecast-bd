# Assumptions, verification status and blockers

Last updated: 2026-10-25. Every item states what was actually checked. "Unverified" means exactly that.

## Verified

| ID | What | How it was verified |
| --- | --- | --- |
| V1 | DGHS epi weeks match the CDC (MMWR) rule for 2026 | `epiweeks` gives W15 on Sun 12 Apr 2026 and W42 for 18-24 Oct 2026, matching two DGHS dashboard observations (12 Apr: W15 equal to that day's 13 cases; 20 Oct: W42 after three days of reports). |
| V2 | DGHS reporting areas: 8 divisions (Dhaka excluding the city corporations), DNCC, DSCC | DGHS daily releases reprinted by BSS, Observer and Ittefaq in August 2026. |
| V3 | Release parser reads real reprints correctly | 6 real 2026 reprints in `tests/fixtures/`; all parsed as hand-checked. 2 of the 6 are incomplete (areas sum to 640 vs 730 and 701 vs 702); the parser flags both. |
| V4 | Leakage test L10 detects leaks | A deliberately injected leak (ignoring `as_of`) made all 4 leakage cases and 2 related tests fail; restored code passes. |
| V5 | Test suite | 49 tests pass locally (Python 3.12 on 2026-10-22; re-run Python 3.13.5 on 2026-10-25, `49 passed in 18.76s`). Model tests use synthetic data and verify mechanics only. |
| V7 | Data workflows could not import the package | `probe`, `scrape` and `forecast` ran `python -m denguecast...` without `src` on the path (`ModuleNotFoundError` reproduced locally). Added `PYTHONPATH: src` to those jobs. |
| V6 | `requirements.txt` was incomplete | `models.py` uses `lightgbm.LGBMRegressor`, which needs scikit-learn; on a clean venv the 4 Model A / ensemble tests failed with `LightGBMError: scikit-learn is required`. Added `scikit-learn` (plus `optuna`, `matplotlib` per Step 1); all 49 then pass. No code or test changed. |

## Step 0: Mendeley z5mvwrfgsz v1 check (2026-10-25, 2022-2023 rows only)

Downloaded by `python -m denguecast.probe` run locally on 2026-10-25 07:57 UTC (internet reachable from the team laptop); all files hashed in `data/archive/raw_manifest.csv`, report in `docs/probe_report.md`. Inspection read only rows whose date ends in `22` or `23`; 2024 rows were filtered out while reading and never printed or summarised (only their row count, 366, was seen while checking the date format).

| Check | Finding |
| --- | --- |
| Files | 8 CSVs, one per division: Barisal, Chittagong, Dhaka, khulna, Mymensingh, Rajshahi, Rangpur, Sylhet (+ a transaction-receipt PDF, not data) |
| Licence | CC BY 4.0 (API `data_licence` field): reuse allowed with credit |
| Frequency | Daily. Date format `dd-mm-yy` (first field reaches >12, second never does) |
| Coverage | 365 rows for 2022 and 365 for 2023 in every file: no missing days |
| Values | Column `effected-<division>` (Dhaka.csv: `Division`,`effected`). Stored as floats (`"0.0"`); every 2022-2023 value is a non-negative whole number; no empty cells |
| DNCC / DSCC | **Not separate.** A single `Dhaka` series |
| National series | **None in the dataset.** Sum of the 8 files: 2022 = 62,124; 2023 = 321,209 |
| Meaning of `Dhaka` | Sum of 8 files is within 0.4% (2022) and 0.01% (2023) of the DGHS annual hospitalisation totals widely reported (about 62,382 and 321,179, from memory; not used as data). So `Dhaka` almost certainly = whole Dhaka division **including** DNCC and DSCC. Not verified against an official breakdown |
| Metric | "effected" = daily new hospital admissions (inferred from totals matching DGHS admissions) |
| Also contains | Daily weather columns (out of scope, D3) |

Consequence for the plan (needs a GATE 2 decision): the archive's `DHAKA_DIV` means Dhaka division *excluding* the city corporations, which this dataset cannot provide. Backtest units can only be the 7 other divisions, a whole-Dhaka unit, and a NATIONAL series constructed as the sum of the 8 files.

Mendeley cgwjshkx5k v2 (monthly, optional cross-check): downloaded, CC BY 4.0; its `Division` column did not parse cleanly with a plain read; not used.

DGHS dashboard: HTTP 403 (7 bytes) to an automated request from this laptop. No division-table parser is possible from what was retrieved; live data relies on manual entry (guide Section 14 fallback).

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

## Team decisions D1-D9 (pre-registration amendments; to be written into the pre-registration before lock)

Status: **awaiting team confirmation at GATE 1.** Source: `DENGUECAST_GUIDE.md` Section 5.

| ID | Decision |
| --- | --- |
| D1 | Test season = 2024 only. 2025 dropped because no daily source is confirmed. Decided before seeing any 2024 or 2025 results. |
| D2 | H3, H5 and H6 deferred and reported as planned work. H1 (primary) and H2 evaluated on 2024; H4 (phases) descriptive. |
| D3 | Model A runs without weather or population features (P2). Each forecast's metadata records the features used. |
| D4 | B3 = ARIMA(1,1,1) on log(1+y) with two Fourier harmonics while fewer than 3 training seasons exist; SARIMA(1,1,1)(1,0,0,52) from 3 seasons on (P3). |
| D5 | Wording clarifications (P1): A5 (re-centred, pooled baseline intervals), A6 (final truth as known 14 days after week end), A7 (MAD floored at 1). |
| D6 | Comparator = whichever of B1 and B2 has lower WIS on the 2023 validation; recorded in `docs/comparator.md` after validation and before the 2024 run. |
| D7 | Lock date = Saturday 24 October 2026, before any 2024 data is ingested. |
| D8 | Tuning budget: at most 20 Optuna trials (pre-registration allows up to 50). |
| D9 | Model A refit every 4 weeks within the replay; B3 refit every week. |

## Blockers

| ID | Blocker | What unblocks it | Status |
| --- | --- | --- | --- |
| B1 | Mendeley 2022-2024 dataset unverified | Probe run locally 2026-10-25; see Step 0 section | **Resolved** (structure differs from plan: see GATE 2 decision) |
| B2 | DGHS dashboard raw HTML has never been inspected, so no division-table parser exists; the scraper stores raw pages only | Probe report shows how the dashboard delivers its tables | Dashboard returned HTTP 403 on 2026-10-25; manual entry only |
| B3 | Creating and pushing the public repository needs the team's GitHub account | Team creates the repo and pushes this code | Waiting for team |
| B4 | The first live forecast (Sat 24 Oct, origin W42) needs W42 values for every unit plus at least 20 weekly log ratios of history | Either B2 resolved, or the 7 daily releases for 18-24 Oct transcribed into `data/manual/daily_releases.csv` with sources, plus enough earlier weeks | Open |
| B5 | Weather (Open-Meteo) and population (census 2022) are not ingested | After B1 confirms Open-Meteo access | Open |
| B6 | Model A and B3 are untrained on real data; hyperparameters untuned | After Mendeley 2022-2023 ingestion (B1) | Open |
| B7 | Schedule: Step 1 started on Sun 25 Oct 2026, after the planned lock date (D7, Sat 24 Oct) and after the live-forecast deadline for origin 2026-10-24 (Sun 25 Oct 12:00 BDT). No `forecasts/2026-10-24/` exists. Per guide Step 7, this is recorded as missed, never back-dated | Team decides at GATE 1: revised lock date, whether the first live forecast becomes origin 2026-10-31, and log in `docs/DEVIATIONS.md` | Open |

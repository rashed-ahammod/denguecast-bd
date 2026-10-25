# DengueCast BD

Probabilistic forecasts of **weekly dengue hospital admissions in Bangladesh, 1-4 weeks ahead**, for the
whole country and its divisions, built only from public data and evaluated under a plan that was fixed
(git tag `prereg-v1`) before the test season was loaded.

**Dashboard:** https://rashed-ahammod.github.io/denguecast-bd/

Not a clinical tool. Forecasts target admissions reported by DGHS, not infections.
HealthSphere AI track, International AI Builders Congress 2026 (CloudCamp Bangladesh).

## The problem

Bangladesh had its worst dengue year on record in 2023 (over 320,000 reported hospitalisations). Hospitals and
health planners see the wave arrive but have no public, honestly evaluated forecast of how many admissions are
coming in the next few weeks, with an uncertainty range they can plan against.

## What we claim, and what we do not

> A pre-registered, leakage-free backtest on the 2024 season, compared against simple baselines, plus live
> forecasting that started on 24 October 2026 with public timestamps and continues weekly.

We do **not** claim live accuracy (one live forecast exists and cannot be scored yet), outbreak prediction in
general, or any number not produced by the code in this repository.

## Approach

| Step | What | Where |
| --- | --- | --- |
| Archive | Every value stored as published, append-only, with when it became available; raw files kept with SHA-256 hashes | `src/denguecast/archive.py`, `data/` |
| One data door | All modelling code reads data only through `get_data(as_of=t)`, which returns what was known at time t | `archive.get_data` |
| Cleaning | Pre-registered rules: epi weeks (CDC rule), incomplete weeks left missing, past-only outlier clipping, final truth = value known 14 days after the week | `cleaning.py` |
| Baselines | B1 persistence, B2 seasonal naive, B3 ARIMA with Fourier seasonality | `baselines.py`, `models.py` |
| Model A | LightGBM quantile regression pooled across units (lags, growth, unit), tuned on 2023 only | `models.py` |
| Ensemble | Equal-weight quantile average of Model A and B3 | `models.py` |
| Replay | Forward-chaining: for every week, forecast from what was available on Saturday 23:59 BDT | `evaluate.py` |
| Scoring | Weighted interval score (WIS), 50%/90% coverage, relative WIS with a block bootstrap, count and log scales | `scoring.py`, `evaluate.py` |
| Live | Weekly forecast written to `forecasts/<origin>/`, never overwritten, with creation time and `late` flag | `live_forecast.py` |

Data: daily division-wise admissions 2022-2024 from Mendeley dataset z5mvwrfgsz v1 (Naher 2026, CC BY 4.0);
live 2026 values transcribed from DGHS daily releases. See `DATA_SOURCES.md`.

## Results

See `docs/results.md` (generated from `results/` by `scripts/write_results.py`; every number comes from those files).

**2024 test season (single run, commit `90e282a`, comparator: persistence):**

- **H1 (primary) SUPPORTED:** ensemble relative WIS vs persistence, horizons 1-3 = **0.58** (95% bootstrap interval 0.44-0.74); log scale 0.79 (0.73-0.87).
- **H2 SUPPORTED:** ensemble interval coverage, horizons 1-3: 50% intervals 46.8%, 90% intervals 83.6% (pre-registered bands 42-58% and 82-95%).
- 1782 forecasts scored per model (9 units x 52 weeks x 4 horizons, less 4 target weeks in 2025 without truth).
- H4 (phases), all breakdowns and the 2023 VALIDATION results (optimistic) are in `docs/results.md`.


## What is verified, assumed and next

**Verified** (details and outputs in `docs/ASSUMPTIONS_AND_BLOCKERS.md`):
- Test suite passes locally and in GitHub Actions.
- Leakage test: a forecast from the full archive equals one from an archive cut at the forecast time; a deliberately injected leak makes all leakage tests fail (mutation proof).
- Append-only check: edited archive rows or overwritten forecasts fail CI.
- Mendeley data: daily, no gaps in 2022-2023, licence CC BY 4.0. Its eight divisions sum to the published DGHS annual totals within 0.4%.

**Assumed / limitations:**
- The 2022-2024 data has no separate Dhaka city corporations and no national series: national = sum of the eight divisions; Dhaka is evaluated as the whole division.
- Only one test season (2024); 2023 results are validation and therefore optimistic.
- The first live forecast was made late (14:44 BDT on 25 Oct, after the 12:00 deadline) and is flagged `late: true`. Its W42 inputs were transcribed from newspaper reprints; the 20 Oct release is contradictory across sources, so Rajshahi and Dhaka were not forecast that week.
- No OSF registration: the plan is fixed by the public git tag `prereg-v1`. All changes are in `docs/DEVIATIONS.md`.
- No weather or population features yet; reporting coverage, serotypes and immunity are not in public data.

**Next:** weekly live forecasts every Saturday (workflow `forecast`), live scoring once truth is final, weather features (Open-Meteo), a parser for the DGHS dashboard, Bangla bulletins.

## Run it

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # .venv/bin/python on Linux/macOS
.venv/Scripts/python -m pytest -q                            # full test suite
.venv/Scripts/python -m denguecast.ingest_mendeley           # 2022-2023 into the archive
.venv/Scripts/python -m denguecast.evaluate --season 2023    # validation replay
.venv/Scripts/python -m denguecast.ingest_manual             # live releases from data/manual/
.venv/Scripts/python -m denguecast.live_forecast             # this week's forecast
.venv/Scripts/python scripts/build_site.py                   # dashboard -> site/index.html
```

2024 is locked: it can only be loaded with `DENGUECAST_ALLOW_TEST_SEASONS=1`, which is set for the single test run only.

## Credits and licence

Case data: Directorate General of Health Services (DGHS), Bangladesh. Dataset: Naher (2026), "Division-wise daily
dengue cases with weather, 2022-2024", Mendeley Data, DOI 10.17632/z5mvwrfgsz.1, CC BY 4.0. Code: MIT licence.

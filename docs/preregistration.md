# DengueCast BD: analysis plan (locked by git tag `prereg-v1`)

**Status.** This plan is fixed by the git tag `prereg-v1` on the public repository
https://github.com/rashed-ahammod/denguecast-bd, pushed **before any 2024 data was ingested or inspected**.
It was not registered on OSF (team decision, 25 Oct 2026; see `docs/DEVIATIONS.md`). The public
commit and tag timestamps are the evidence of when it was fixed. Every later change goes in
`docs/DEVIATIONS.md` before it is used.

It consolidates the specification in `DENGUECAST_GUIDE.md` (Sections 3, 5, 6, 11) and the
amendments D1-D11 recorded in `docs/ASSUMPTIONS_AND_BLOCKERS.md`.

## 1. Target and units

- Target: new dengue hospital admissions reported by DGHS per unit per epi week (Sunday-Saturday by report date, CDC/MMWR rule).
- Horizons 1-4 weeks; quantiles 0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975 (sorted, negatives set to 0).
- Backtest units (D10): NATIONAL (sum of the 8 division files of the Mendeley data), DHAKA_DIV_TOTAL (Dhaka division including DNCC and DSCC), CHATTOGRAM_DIV, BARISHAL_DIV, KHULNA_DIV, RAJSHAHI_DIV, RANGPUR_DIV, MYMENSINGH_DIV, SYLHET_DIV.
- Live units additionally: DHAKA_DIV (outside the city corporations), DNCC, DSCC.

## 2. Data

- Development and test: Mendeley z5mvwrfgsz v1 (Naher 2026, CC BY 4.0), daily division-wise admissions 2022-2024. Train 2022, validation 2023, **test 2024 only** (D1). 2025 is not evaluated.
- Live: DGHS daily releases (manual entry, two people, exact-sum check).
- Every read goes through `archive.get_data(as_of=t)`; values count as available at 12:00 UTC on the report date (A4).

## 3. Cleaning (pre-registration Section 5 rules, as implemented in `cleaning.py`)

Weeks with fewer than 7 reported days are missing (rules 2-4); consistency flag at 2% (rule 7); city-corporation merge (rule 8); outliers: trailing 8-week median and MAD (floored at 1), beyond 5 x MAD, model inputs clipped, truth unchanged (rule 9, A7). Final truth = weekly value as known 14 days after the week ends; where no epi-week value exists, the sum of the 7 daily values (A6, D10).

## 4. Models

- B1 persistence; B2 seasonal naive (52 weeks). Intervals from past log1p ratios, re-centred, pooled across units below 20 ratios (A5).
- B3: per-unit ARIMA(1,1,1) on log1p with two Fourier harmonics below 3 seasons of data, SARIMA(1,1,1)(1,0,0,52) from 3 seasons (D4); refit every week (D9).
- Model A: LightGBM quantile regression, one model per (horizon, quantile), pooled, direct; features log1p lags 1-8, 2- and 4-week growth, unit code, missing indicator; no weather or population (D3); refit every 4 weeks (D9). Hyperparameters tuned on 2023 with Optuna TPE, seed 2026, 20 trials (D8); the tuned values are fixed in `results/2023/model_a_params.json`.
- Ensemble: equal-weight quantile-wise mean of Model A and B3.
- Comparator: whichever of B1 and B2 has lower mean WIS on the 2023 validation (D6), recorded in `docs/comparator.md`.

## 5. Replay and scoring

Forward-chaining replay: for each epi week of the season, forecasts are made as of Saturday 23:59 BDT from data available then. Scoring: WIS (alphas 0.05, 0.10, 0.20, 0.50), 50% and 90% coverage, on count and log1p scales; only forecasts produced by every model are compared; weeks with missing truth are excluded and counted. Relative WIS = mean model WIS / mean comparator WIS; 95% interval from a moving-block bootstrap over origin weeks (block 4, 2,000 resamples, seed 2026).

Phases (scoring only): centred 3-week moving average of truth; peak (within 2 weeks of the season maximum), low (< 10% of the maximum), growth (3-week growth > +10%), decline (< -10%), plateau.

## 6. Hypotheses and decision rules (2024 test season)

| Hypothesis | Supported | Partly supported | Not supported |
| --- | --- | --- | --- |
| H1 (primary): ensemble WIS < comparator WIS, all units, horizons 1-3 | Upper 95% bound of relative WIS < 1 | Point estimate < 1, interval includes 1 | Point estimate >= 1 |
| H2: calibration of the ensemble, horizons 1-3 | 90% coverage in [0.82, 0.95] and 50% coverage in [0.42, 0.58] | One of the two in its band | Neither |
| H4: phases | Descriptive: relative WIS and coverage per phase | | |

H3, H5 and H6 are deferred (D2). Horizon 4 is secondary. Every result is reported on both scales, whatever the verdict. The 2024 run is done once; any re-run is a logged deviation.

# DengueCast BD — Project Guide for Claude Code

**Read this whole file before doing anything.** It is the single source of truth for building DengueCast BD. Work through Section 13 (the 72-hour plan) step by step. Stop at every gate marked **GATE** and wait for the user.

- Project: DengueCast BD (HealthSphere AI track), International AI Builders Congress 2026, organised by CloudCamp Bangladesh.
- Team: student research team.
- **Final project due: Monday 26 October 2026.** Today is Friday 23 October 2026. Plan for about 72 hours of work.
- Specification documents: this file, and the pre-registration (exported to `docs/preregistration.md`). Where they disagree, stop and ask the user.

---

## 1. What we are building

A system that produces **probabilistic forecasts of weekly dengue hospital admissions** in Bangladesh, **1–4 weeks ahead**, for the whole country, each division and the two Dhaka city corporations. It is built **only from public data** and evaluated under a **pre-registration**, so its results can be trusted.

For the 26 October submission, the system must have:

1. A working, tested pipeline: archive, cleaning, baselines, models, scoring.
2. A **pre-registered, leakage-free backtest**: validation on 2023, then a single test run on 2024.
3. **The first live forecast**, published with a public GitHub timestamp on Saturday 24 October.
4. A simple dashboard and a written results report.

It is **not** a clinical tool. It forecasts admissions reported by DGHS, not infections.

---

## 2. Rules (copy this section into `CLAUDE.md` in Step 1)

1. **Never invent, estimate or "fill in" data.** If a source is missing, unreachable or ambiguous, stop, report it, and log it in `docs/ASSUMPTIONS_AND_BLOCKERS.md`.
2. **Never say a task is done without running the full test suite and showing the output.**
3. **All data reads go through `archive.get_data(as_of=t)`.** No other module may open `data/archive/observations.csv`.
4. **Archive files are append-only.** Corrections are new rows. Published files in `forecasts/` are never modified or deleted.
5. **The 2024 test season is locked** until the user says the pre-registration is locked and asks for the test run (Step 9). Never set `DENGUECAST_ALLOW_TEST_SEASONS=1` otherwise. Before that, never load, print, summarise or plot 2024 or 2025 rows. When reading a file that contains 2024 rows, filter them out while reading.
6. **No future information in any forecast:** not in features, scaling, imputation, clipping, smoothing, tuning or early stopping.
7. **Inspect existing files before changing them.** Make small commits with clear messages.
8. **Synthetic data is allowed only inside tests**, labelled SYNTHETIC, and is never written to `data/` or `forecasts/`.
9. **Record every assumption** in `docs/ASSUMPTIONS_AND_BLOCKERS.md`. After the pre-registration is locked, any change to the plan goes in `docs/DEVIATIONS.md` before it is used.
10. **Ask the user only when a decision or access genuinely needs them**, and always at a **GATE**.
11. **Never weaken a test** on leakage, append-only behaviour or season locking to make something pass.
12. **Create directories explicitly** (`mkdir -p a; mkdir -p b`). Do not rely on shell brace expansion, and list folders afterwards to prove they exist.

---

## 3. Fixed specifications

| Item | Value |
| --- | --- |
| Units | `NATIONAL`, `DHAKA_DIV` (Dhaka division excluding DNCC and DSCC), `CHATTOGRAM_DIV`, `BARISHAL_DIV`, `KHULNA_DIV`, `RAJSHAHI_DIV`, `RANGPUR_DIV`, `MYMENSINGH_DIV`, `SYLHET_DIV`, `DNCC`, `DSCC`. Fallback merged unit `DHAKA_CITY`, used only when DNCC or DSCC is missing for a whole year |
| Epi weeks | Sunday–Saturday by DGHS report date, CDC/MMWR rule (`epiweeks` package, `system="cdc"`) |
| Epi-week checks | 12 Apr 2026 = 2026 W15; 18–24 Oct 2026 = W42; 3 Jan 2026 = 2025 W53; 4 Jan 2026 = 2026 W1 |
| Primary target | New admissions per unit per epi week |
| Secondary target | Patients currently admitted at week end (deferred; see Section 5) |
| Not forecast | Deaths |
| Horizons | 1, 2, 3, 4 weeks |
| Quantiles | 0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.975 (sorted, negatives set to 0) |
| Seasons | Train 2022; validation 2023; **test 2024 only** (locked); live from 24 Oct 2026 |
| Metrics | Weighted interval score (WIS) with alphas 0.05, 0.10, 0.20, 0.50; 50% and 90% coverage; relative WIS; WIS on log1p scale |
| Random seed | 2026 everywhere |
| Live forecast time | Saturday 16:30 UTC (22:30 BDT); must be committed before Sunday 12:00 BDT |
| Scraper time | Daily 16:00 UTC (22:00 BDT), retry 03:00 UTC (09:00 BDT) |

---

## 4. Scope for 26 October, and what we may claim

**In scope:** steps in Section 13.

**Out of scope for this submission** (list them as next steps, never as results):

- Weather and population features (Model A runs without them).
- H3 (weather-forecast ablation), H5 (live accuracy), H6 (hospital load).
- The 2025 test season (no confirmed daily source).
- Bangla bulletins and the live scorecard.

**What the submission may claim:**
> A pre-registered, leakage-free backtest on the 2024 season, compared against simple baselines, plus live forecasting that started on 24 October 2026 with public timestamps and continues weekly.

**Never claim** live accuracy, outbreak prediction in general, or any number not produced by the code in this repository.

---

## 5. Team decisions: pre-registration amendments

These are the team's decisions for the 26 October scope. They must be written into the pre-registration **before it is locked in Step 6**. If the user has not confirmed them, ask at GATE 1.

| ID | Decision |
| --- | --- |
| D1 | **Test season = 2024 only.** 2025 is dropped because no daily source is confirmed. Decided before seeing any 2024 or 2025 results. |
| D2 | **H3, H5 and H6 are deferred** and reported as planned work. The primary hypothesis H1 and secondary H2 are evaluated on 2024; H4 (phases) is descriptive. |
| D3 | **Model A runs without weather or population features** (P2). Each forecast's metadata records the features used. |
| D4 | **B3 = ARIMA(1,1,1) on log(1+y) with two Fourier harmonics** while fewer than 3 seasons of training data exist; SARIMA(1,1,1)(1,0,0,52) from 3 seasons on (P3). |
| D5 | **Wording clarifications (P1):** baseline intervals re-centred on the point forecast and pooled across units when a unit has fewer than 20 ratios (A5); final truth = the weekly value as known 14 days after the week ends (A6); the outlier rule floors the MAD at 1 (A7). |
| D6 | **Comparator** = whichever of B1 and B2 has lower WIS on the 2023 validation; recorded in `docs/comparator.md` after validation and before the 2024 run. |
| D7 | **Lock date = Saturday 24 October 2026**, before any 2024 data is ingested. |
| D8 | **Tuning budget:** at most 20 Optuna trials (the pre-registration allows up to 50). |
| D9 | **Model A refit every 4 weeks** within the replay, as pre-registered; B3 refit every week. |

---

## 6. Repository layout and module specifications

```
CLAUDE.md                     rules (Section 2)
DENGUECAST_GUIDE.md           this file
README.md, LICENSE (MIT), DATA_SOURCES.md, requirements.txt, pyproject.toml
src/denguecast/
  config.py  epiweek.py  archive.py  scrape.py  probe.py
  release_parser.py  ingest_manual.py  ingest_mendeley.py
  cleaning.py  baselines.py  models.py  scoring.py
  evaluate.py  live_forecast.py
tests/  (pytest; fixtures in tests/fixtures/)
data/archive/observations.csv   data/archive/raw_manifest.csv
data/raw/   data/manual/daily_releases.csv   data/quality_log.csv
forecasts/<origin Saturday>/<model>.csv and .json
results/   (evaluation outputs)
site/      (static dashboard)
docs/  preregistration.md  ASSUMPTIONS_AND_BLOCKERS.md  DEVIATIONS.md
       probe_report.md  comparator.md  results.md
scripts/  check_append_only.py  build_site.py
.github/workflows/  tests.yml  scrape.yml  probe.yml  forecast.yml
```

`requirements.txt`: pandas, numpy, requests, epiweeks==2.4.0, lightgbm, statsmodels, scipy, optuna, matplotlib, pytest. `pyproject.toml`: pytest `pythonpath = ["src", "tests"]`.

### Reference implementation

The team may have a reference repository from an earlier session (`denguecast-bd.zip`). It already implements `config`, `epiweek`, `archive`, `scrape`, `probe`, `release_parser`, `ingest_manual`, `cleaning`, `baselines`, `scoring`, `models`, `live_forecast`, the append-only check and four workflows, with 49 passing tests. **If it is present, start from it** (Step 1 tells you how). Otherwise build each module to the specification below.

### 6.1 `config.py`
All values from Section 3, plus paths, `METRICS = (admissions, currently_admitted, deaths, cumulative_admissions)`, and `test_seasons_unlocked()`, which returns True only when `DENGUECAST_ALLOW_TEST_SEASONS == "1"`. **Set `TEST_SEASONS = {2024, 2025}`** (2025 stays locked even though it is out of scope).

### 6.2 `archive.py`
- Columns: `unit, reference_date (YYYY-MM-DD; Saturday for period=epiweek), period (day|epiweek), metric, value, source, source_url, vintage_type (live|first_reported|final), available_at (UTC ISO), available_at_basis (retrieved|published|assumed), retrieved_at (UTC ISO), raw_sha256, note`.
- `append_observations(df, archive_file=None)`: validate units, metrics, periods, vintages and bases; reject timestamps without a timezone; store non-integer or negative values as empty with the note "invalid published value"; skip exact duplicates; append mode only.
- `save_raw_snapshot(content, source, url, extension)`: store bytes unchanged under `data/raw/<source>/<YYYY-MM-DD>/<HHMMSS>_<sha12>.<ext>`; don't store identical content twice; log every retrieval with its SHA-256 in `raw_manifest.csv`.
- `get_data(as_of, metrics=None, units=None, period=None, sources=None, include_test_seasons=False, archive_file=None)`: keep rows with `available_at <= as_of`; return the latest version per (unit, reference_date, period, metric); drop epi years 2024–2025 unless `include_test_seasons=True` **and** the variable is "1" (otherwise raise `SeasonLockError`); a naive `as_of` raises `ValueError`.
- `write_truncated_archive(as_of, src, dst)` for the leakage test.

### 6.3 `release_parser.py`
Parses DGHS release text as reprinted by BSS, UNB and newspapers. Two patterns: "`<number>` [patients were hospitalised] in [the] `<area>`" and "`<area>` [Division] [(…)] recorded|reported|logged `<number>`". Handle number words one to twenty, leading zeros (warn), "Dhaka North/South City Corporation", DNCC/DSCC, a bare "Dhaka" (read as Dhaka division, with a warning), and the Chittagong/Barisal spellings. The stated total comes from "of the `<N>`". Return counts, stated total and warnings; warn when the areas don't add up. **Never adjust numbers.** Test fixtures: Section 16.

### 6.4 `ingest_manual.py`
File `data/manual/daily_releases.csv` with columns `report_date,unit,admissions,stated_total,source_url,entered_by,note`. Reject rows without a source URL; per date require one consistent `stated_total`, no duplicate units, and an exact sum, otherwise reject the whole date and print why. Add a NATIONAL row equal to `stated_total`. Store with source `dghs_press_release`, vintage `first_reported`, `available_at` = report date 12:00 UTC, basis `assumed`. Exit 1 if any date was rejected.

### 6.5 `ingest_mendeley.py`
Reads the Mendeley dataset `z5mvwrfgsz` v1 (division-wise daily cases, 2022–2024) from the raw files.
- Parameter `years`: default `{2022, 2023}`. While reading, **filter out other years before printing or summarising anything.**
- An explicit name-to-unit mapping table; stop and report any name that can't be mapped.
- Store with source `mendeley_z5mvwrfgsz`, vintage `final`, `available_at` = report date 12:00 UTC, basis `assumed`.
- Ingesting 2024 is allowed only in Step 9, with the variable set.
- Print a data report: days per unit, missing days, whether DNCC and DSCC are separate, and whether a national series exists. If there's no national series, **don't construct one silently**: report it at GATE 2.

### 6.6 `cleaning.py` (pre-registration Section 5)
Everything causal except `final_truth`; every action goes into a `QualityLog` appended to `data/quality_log.csv`.
- `daily_to_weekly(daily, log, cumulative=None)` (rules 2–4): sum into epi weeks. Recover a run of missing days when the cumulative count is known the day before the gap and on the first reported day after it, in the same calendar year: gap = cum_after − cum_before − value_on_day_after, split by missing days per week, flag "recovered". Otherwise the week is NaN with flag "missing". Weeks with fewer than 7 days are missing, never partial sums.
- `consistency_check` (rule 7): flag weeks where units differ from NATIONAL by more than 2%; change nothing.
- `merge_city_corporations_if_incomplete` (rule 8).
- `flag_outliers` (rule 9): trailing 8-week median and MAD excluding the current week; flag beyond 5 × MAD, with the MAD floored at 1; add `value_clipped` for model inputs; never change `value`.
- `final_truth(unit, week_end, metric, evaluated_at)` (rules 5–6): value as known 14 days after the week ends, with source priority `dghs_dashboard_epiweek`, `dghs_press_release`, `who_searo_bulletin`, `newspaper`, then `mendeley_z5mvwrfgsz`. Returns `(value, provisional)`.

### 6.7 `baselines.py`
- `persistence(history, origin, on_missing="raise"|"skip")`: median at every horizon = origin week value. Intervals: empirical quantiles of past log1p ratios between week w+h and week w (weeks ≤ origin only), re-centred so the median ratio is 0. Use the unit's own ratios if it has ≥ 20, otherwise pooled across units; if still < 20, raise `InsufficientHistory`.
- `seasonal_naive`: median = same week 52 weeks earlier; intervals from past log1p ratios y_t / y_(t−52w), same rules.
- Output columns: `unit, origin_week_end, horizon, target_week_end, quantile, value, interval_basis`.

### 6.8 `models.py`
- `model_a`: LightGBM quantile regression, one model per (horizon, quantile), pooled across units, direct strategy. Features: log1p admissions lags 1–8 (lag 1 = origin week), 2- and 4-week growth, unit code (categorical), missing indicator. Training rows only where target week ≤ origin. Deterministic: seed 2026, `deterministic=True`, one thread. Regular weekly index (`asfreq("7D")`) so row shifts equal week shifts. Must support **fitting once and predicting at later origins** (refit every 4 weeks, D9).
- `b3_arima`: per unit on log1p; ARIMA(1,1,1) with two Fourier harmonics below 3 seasons, else SARIMA(1,1,1)(1,0,0,52); quantiles from the normal predictive distribution on the log scale.
- `ensemble`: equal-weight quantile-wise mean of Model A and B3, re-sorted; raise if members don't cover the same forecasts.

### 6.9 `scoring.py` (pre-registration Section 9)
WIS = 1/(K + ½) × (½|y − m| + Σ_k (α_k/2) × IS_αk), with IS_α = (u − l) + (2/α)(l − y)·1[y < l] + (2/α)(y − u)·1[y > u], K = 4, α = 0.05, 0.10, 0.20, 0.50, read from the 9 quantiles. Provide `score_forecasts(forecasts, truth, log_scale=False)` (wis, abs_error, cov50, cov90; drop missing truth and count it) and `relative_wis(model, comparator)`.

### 6.10 `evaluate.py` (forward-chaining replay)
- `replay(season, models)`: for each epi week W of the season, `as_of` = Saturday of W at 23:59 BDT (17:59 UTC). Build each model from `live_forecast.weekly_series(as_of)`, forecast horizons 1–4, and score against `final_truth`.
- Refuse to run on 2024 or 2025 unless the test-season variable is set.
- Output to `results/<season>/`: forecasts, scores, and a summary by horizon, unit and epidemic phase, on both scales.
- Phase labels (scoring only): each unit's final truth smoothed with a centred 3-week moving average; then, first rule that applies: **peak** (within 2 weeks of the season maximum), **low** (below 10% of the season maximum), **growth** (3-week growth above +10%), **decline** (below −10%), **plateau** (otherwise).
- `bootstrap(scores_model, scores_comparator)`: moving-block bootstrap over origin weeks, block length 4, 2,000 resamples, seed 2026, keeping all units and horizons of a week together; returns relative WIS with a 95% interval.

### 6.11 `live_forecast.py`
- `weekly_series(as_of, archive_file=None)`: weekly admissions per unit as known at `as_of`; published epi-week rows preferred over aggregated daily rows; applies rules 8 and 9.
- `latest_complete_origin`: latest epi week ending on or before `as_of` (Bangladesh time) with an observed NATIONAL value.
- `build_forecast(as_of, model, archive_file=None)`: **pure**. It reads data only through `get_data(as_of=...)` and never looks at the clock. Model input is `value_clipped`.
- CLI: `as_of` = now; writes `forecasts/<origin>/<model>.csv` and `.json`; exit 3 if the file already exists (never overwrite); exit 2 with "NOT PUBLISHED" if data is insufficient; metadata records the git commit, creation time and `late`.

### 6.12 Tests that must exist
- Epi-week checks (Section 3).
- Archive: append-only, idempotent, as-of versions, naive timestamps rejected, invalid values, unknown unit, season lock, raw-snapshot hashing.
- Parser: the six fixtures in Section 16.
- Manual ingest: consistent date accepted; sum mismatch rejected; missing source rejected.
- Cleaning: one test per rule, including that a future spike doesn't change earlier outlier flags.
- Baselines: median equals last value; data after the origin changes nothing; too little history raises; seasonal naive uses 52 weeks back.
- Scoring: WIS = 0 for a perfect forecast; hand-computed case (quantiles 10, 20, …, 90 and y = 95 gives WIS = 116.5 / 4.5); WIS equals the mean quantile score 2(1{y ≤ q} − τ)(q − y) over the 9 quantiles on 200 random cases.
- Models (SYNTHETIC): shapes, sorted quantiles, determinism, no use of post-origin data.
- **Leakage (L10):** a synthetic 2022–2023 archive with later revisions (values doubled, available 30 days later); for at least four `as_of` times, `build_forecast` on the full archive equals `build_forecast` on `write_truncated_archive(as_of)`.
- Code guard: only `archive.py` and `config.py` mention `observations.csv`; season split and quantiles match Section 3.
- **Mutation proof** (run once and show the output): temporarily make `get_data` ignore `as_of`; the leakage tests must fail; restore the code.

---

## 7. Data sources

| Source | Use | Notes |
| --- | --- | --- |
| [DGHS Dengue Dynamic Dashboard](https://dashboard.dghs.gov.bd/pages/heoc_dengue_v1.php) | Live 2026 data; raw pages archived daily | The table parser is written only after inspecting a stored raw page |
| DGHS daily releases (dashboard press release; reprints by BSS, UNB, newspapers) | Manual entry of the 7 releases for W42 (18–24 Oct 2026) | Reprints can omit areas: always check the sum |
| [Mendeley z5mvwrfgsz v1](https://data.mendeley.com/datasets/z5mvwrfgsz/1), Naher (2026), DOI 10.17632/z5mvwrfgsz.1 | Development (2022–2023) and test (2024) data | **Unverified until Step 0** |
| [Mendeley cgwjshkx5k v2](https://data.mendeley.com/datasets/cgwjshkx5k) | Monthly cross-check only | Optional |

Credit DGHS and the dataset authors in `DATA_SOURCES.md` and the README, and check each dataset's licence.

---

## 8. GitHub Actions workflows

All committing workflows use `permissions: contents: write`, concurrency group `data-commit`, Python 3.12, and `git pull --rebase` before `git push`.

- `tests.yml`: on push and pull request; installs requirements, runs pytest, runs `scripts/check_append_only.py "${{ github.event.before || 'HEAD~1' }}"`.
- `scrape.yml`: cron `0 16 * * *` and `0 3 * * *`, plus manual; runs `denguecast.scrape` and `denguecast.ingest_manual`; commits `data/`.
- `probe.yml`: manual only; runs `denguecast.probe`; commits `docs/probe_report.md` and `data/`.
- `forecast.yml`: cron `30 16 * * 6`, plus manual with a model input; runs the leakage tests, `ingest_manual`, then `live_forecast`; commits `forecasts/` and `data/`.

`scripts/check_append_only.py <base>`: fails if `observations.csv`, `raw_manifest.csv` or `quality_log.csv` changed other than by appending, or if any file under `forecasts/` or `data/raw/` was modified or deleted; skips when the base doesn't exist. Test it in a temporary clone: an append passes; an edited row and an overwritten forecast fail.

---

## 9. Dashboard (`scripts/build_site.py` → `site/index.html`)

A single self-contained HTML page (charts as matplotlib PNGs embedded in base64; no external requests), published with GitHub Pages:

1. **Latest live forecast:** for each unit, the last 12 weeks of observed admissions plus the median and 50%/90% bands for the next 4 weeks; origin date, creation time and commit hash.
2. **Backtest:** 2024 one-week-ahead forecasts against truth for NATIONAL and three units; a table of relative WIS and coverage by horizon.
3. **Data quality:** counts of recovered, missing and flagged weeks.
4. **Limitations:** the list from Section 15, in plain language.

Every number on the page must come from files in `forecasts/` or `results/`.

---

## 10. Submission deliverables (due Monday 26 October)

The user must confirm the competition's required format and deadline time (GATE 1). Prepare:

1. **Public GitHub repository** with all code, data archive, forecasts and workflows; tests green.
2. **`README.md`:** problem, approach, how to run, results summary, what's verified and what's not.
3. **`docs/preregistration.md`** (locked, tag `prereg-v1`, OSF link) and `docs/DEVIATIONS.md`.
4. **`docs/results.md`:** H1 and H2 verdicts with bootstrap intervals, H4 phase table, all breakdowns, validation results labelled as validation.
5. **First live forecast:** `forecasts/2026-10-24/persistence.csv` and `.json`, committed before Sunday 12:00 BDT.
6. **Dashboard** at the GitHub Pages URL.
7. **Pitch material** (slides or video, as the competition requires), built only from the files above.

---

## 11. Evaluation rules

| Hypothesis | Data | Supported | Partly supported | Not supported |
| --- | --- | --- | --- | --- |
| H1 (primary): ensemble WIS < comparator WIS, all units, horizons 1–3 | 2024 replay | Upper 95% bound of relative WIS < 1 | Point estimate < 1, interval includes 1 | Point estimate ≥ 1 |
| H2: calibration | 2024 replay | 90% coverage in [0.82, 0.95] and 50% coverage in [0.42, 0.58] | One of the two in its band | Neither |
| H4: phases | 2024 replay | Descriptive only: relative WIS and coverage per phase | | |

Report every result whatever the verdict, on both count and log scales. Horizon 4 is secondary. Weeks with missing truth are excluded and counted.

---

## 12. When to stop and ask (GATES)

- **GATE 1 (Friday):** user confirms decisions D1–D9, the submission format and deadline time, and that the GitHub repo exists.
- **GATE 2 (Friday night or Saturday morning):** report the Mendeley data check. If the data is unusable (not daily, divisions missing, large gaps, or a licence forbidding reuse), stop; the user chooses the fallback.
- **GATE 3 (Saturday midday):** the user locks the pre-registration. Don't ingest or open 2024 data until the user says it is locked.
- **GATE 4 (Saturday evening):** manual W42 entries are complete, entered by two people and passing `ingest_manual`, before the live forecast runs.
- **GATE 5 (Sunday morning):** the user explicitly starts the single 2024 test run.

---

## 13. The 72-hour plan

Each step: **do**, **verify**, **done when**. Commit and push after every step.

### Step 0 — Mendeley check (Friday, user + Claude Code, ~30 min)
- **Do:** the user downloads the files from the Mendeley page in a browser and places them in `data/raw/mendeley_z5mvwrfgsz_files/` (or runs the probe workflow). Store each with `save_raw_snapshot` so its hash is logged. Inspect structure **for 2022–2023 only**: columns, daily or not, which areas, whether DNCC/DSCC are separate, gaps, licence.
- **Verify:** a written summary in `docs/ASSUMPTIONS_AND_BLOCKERS.md`.
- **Done when:** GATE 2 is passed.

### Step 1 — Repository and rules (Friday, ~1 h)
- **Do:** if the reference repo is present, unzip it into the repo, run `python -m pytest -q` and confirm 49 tests pass, then add `DENGUECAST_GUIDE.md`. Otherwise build the skeleton and modules 6.1–6.4 with their tests. Create `CLAUDE.md` from Section 2. Add `optuna` and `matplotlib` to requirements. Update `docs/ASSUMPTIONS_AND_BLOCKERS.md` with decisions D1–D9.
- **Verify:** full suite passes; `git push` succeeds; the **tests** workflow is green on GitHub.
- **Done when:** both hold.

### Step 2 — Probe and scraper live (Friday night, ~1 h)
- **Do:** user runs the **probe** workflow; read `docs/probe_report.md`. Enable the **scrape** schedule. If a stored DGHS raw page clearly shows the division tables, write the parser with tests from that page; if not, don't guess: keep storing raw pages and rely on manual entry.
- **Done when:** at least one raw DGHS page is committed by the workflow.

### Step 3 — Ingest 2022–2023 (Saturday morning, ~1.5 h)
- **Do:** write `ingest_mendeley.py` (6.5) with tests; ingest 2022–2023; run cleaning; write a data report (weekly series per unit, recovered and missing weeks, consistency flags).
- **Verify:** `get_data` shows no 2024 rows; the suite passes.
- **Done when:** weekly 2022–2023 series exist for every unit, or the gaps are documented.

### Step 4 — Models and replay engine (Saturday morning, ~2 h)
- **Do:** implement or verify `models.py` (6.8) with the fit-once, predict-later ability, and `evaluate.py` (6.10) with tests (replay refuses 2024 without the variable; bootstrap reproducible with seed 2026).
- **Done when:** the suite passes.

### Step 5 — Validation on 2023 and tuning (Saturday, ~2 h)
- **Do:** run the 2023 replay for B1, B2, Model A, B3 and the ensemble. Tune Model A with Optuna (TPE, seed 2026, at most 20 trials, search space: learning rate 0.01–0.1 log scale, leaves 8–64, min data per leaf 10–100, feature fraction 0.6–1.0, L2 0–10, up to 2,000 trees with early stopping after 100 rounds on the last 8 weeks of each training window), scored by mean 2023 WIS. Write `results/2023/` and `docs/comparator.md`.
- **Verify:** the validation report is labelled VALIDATION.
- **Done when:** `docs/comparator.md` is committed.

### Step 6 — Lock the pre-registration (Saturday midday, user)
- **Do:** the user updates the pre-registration with D1–D9, exports it to `docs/preregistration.md`, commits, tags `prereg-v1`, registers on OSF.io and adds the hash and link.
- **Done when:** GATE 3 is passed. Note: if Step 5 isn't finished by then, lock anyway; D6 already fixes the rule for the comparator.

### Step 7 — First live forecast (Saturday evening)
- **Do:** two people transcribe the official DGHS releases for 18–24 October 2026 (10 areas × 7 days) into `data/manual/daily_releases.csv` with source URLs. Run `python -m denguecast.ingest_manual`; fix only transcription errors against the official source. Dry-run `build_forecast(now, "persistence")` and show origin, units, skipped units and interval basis. Then let the **forecast** workflow run at 22:30 BDT, or run it manually.
- **Verify:** `forecasts/2026-10-24/persistence.csv` and `.json` are committed by the workflow before Sunday 12:00 BDT, with `late: false`.
- **Done when:** both files are on GitHub. If it fails, record it as missed; never back-date.

### Step 8 — Leakage proof and guards (can run in parallel with Steps 3–5)
- **Do:** confirm the leakage tests, the mutation proof and the append-only test in a temporary clone; show the output.
- **Done when:** the output is in `docs/ASSUMPTIONS_AND_BLOCKERS.md` under "Verified".

### Step 9 — The single 2024 test run (Sunday morning)
- **Do (only after GATE 5):** set `DENGUECAST_ALLOW_TEST_SEASONS=1` for this run only; ingest the 2024 Mendeley rows; run the replay with the locked code (tag `prereg-v1` plus logged deviations); compute H1, H2 and H4 (Section 11) with the bootstrap. Write `results/2024/` and `docs/results.md`.
- **Verify:** the run's commit hash and the exact command are recorded in `docs/results.md`.
- **Done when:** `docs/results.md` is committed. **Do not re-run with changes to improve the numbers.** Any re-run is a deviation, logged with its reason.

### Step 10 — Dashboard (Sunday afternoon)
- **Do:** `scripts/build_site.py` → `site/index.html` (Section 9); publish with GitHub Pages.
- **Done when:** the page loads from the public URL.

### Step 11 — README, write-up, pitch (Sunday evening)
- **Do:** README results section, limitations, next steps; pitch material per the competition's format. Every number is copied from `docs/results.md` or the forecast files.

### Step 12 — Final check and submit (Monday)
- Run the checklist in Section 17, then submit before the deadline.

---

## 14. Fallbacks

| Problem | Fallback |
| --- | --- |
| Mendeley data unusable | Stop at GATE 2. The user may choose a within-2026 backtest from the DGHS dashboard's epi-week table, which must be clearly labelled weaker evidence (no separate test season). |
| DGHS dashboard parser not possible | Manual entry (Step 7) only. |
| Model A too slow | Refit every 4 weeks (already planned); reduce Optuna trials; never shorten the replay. |
| Live forecast fails before Sunday 12:00 BDT | Record as missed in `docs/DEVIATIONS.md`; the submission states it honestly. |
| Results are poor | Report them as they are. A credible negative result scores better than an unsupported claim. |

---

## 15. Known assumptions and limitations

- **A1:** the CDC epi-week rule is inferred from two DGHS dashboard observations; re-check at the year boundary.
- **A3:** a bare "Dhaka" in a reprint means Dhaka division outside the city corporations.
- **A4:** where publication time is unknown, values count as available at 18:00 BDT on the report date.
- **A5–A7:** see D5.
- **A9:** live forecasts use 2022–2023 and 2026 history only.
- Targets are reported hospital admissions, not infections.
- Reporting coverage has changed over time; serotype shifts and immunity aren't in public data.
- Division level is too coarse for targeting mosquito control within cities.
- Only one season is tested (2024); 2023 results are validation and therefore optimistic.
- One live forecast exists at submission; it can't yet be scored.

---

## 16. Parser fixtures (real 2026 DGHS releases)

Fetch each page, save the release sentence and URL in `tests/fixtures/release_reprints_2026.json`, and test that every count, total and consistency flag matches.

| Source | Stated total | Areas | Sum | Consistent |
| --- | --- | --- | --- | --- |
| [BSS, 1 Aug 2026](https://www.bssnews.net/news/410800) | 371 | Barishal 69, Chattogram 91, Dhaka 46, DSCC 32, DNCC 57, Khulna 34, Mymensingh 23, Rajshahi 17, Sylhet 2 | 371 | Yes |
| [Observer, 11 Aug 2026](https://observerbd.com/news/587498) | 726 | Barishal 75, Chattogram 81, DSCC 83, DNCC 101, Khulna 107, Mymensingh 37, Rajshahi 65, Rangpur 172, Sylhet 5 | 726 | Yes |
| [BSS, 15 Aug 2026](https://www.bssnews.net/news/414847) | 730 | Barishal 17 (printed "017"), Chattogram 89, Dhaka 66, DSCC 137, DNCC 171, Khulna 123, Mymensingh 27, Rangpur 10 | 640 | No |
| [Ittefaq, 22 Aug 2026](https://en.ittefaq.com.bd/17824/702-fresh-cases-of-dengue-inflection-reported) | 702 | Barishal 115, Chattogram 107, Dhaka 47, DSCC 88, DNCC 123, Khulna 114, Mymensingh 38, Rajshahi 54, Rangpur 15 | 701 | No |
| [Financial Express, 12 Jan 2026](https://today.thefinancialexpress.com.bd/print/one-dies-of-dengue-1768236954) | 33 | Barishal 7, Chattogram 12, Dhaka 2, DSCC 3, DNCC 4, Khulna 2, Mymensingh 1, Rajshahi 2 | 33 | Yes |
| [Financial Express, 30 Mar 2026](https://today.thefinancialexpress.com.bd/print/23-dengue-cases-detected-1774894387) | 23 | Barishal 11, Chattogram 3, Dhaka 6 (bare "Dhaka"), DSCC 2, Khulna 1 | 23 | Yes |

---

## 17. Final checklist before submitting

- [ ] Full test suite passes locally and the **tests** workflow is green.
- [ ] Mutation proof output recorded.
- [ ] Pre-registration locked: tag `prereg-v1`, OSF link, D1–D9 included.
- [ ] `docs/comparator.md` committed before the 2024 run (check commit order).
- [ ] 2024 run done once; command and commit hash in `docs/results.md`.
- [ ] Every hypothesis reported, including any unsupported ones.
- [ ] `forecasts/2026-10-24/` committed before Sunday 12:00 BDT, or the miss is recorded.
- [ ] Dashboard live; every number traceable to a file.
- [ ] README states what is verified, what is assumed and what is next.
- [ ] Data sources credited; licences checked.
- [ ] No claim of live accuracy anywhere.

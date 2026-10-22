# DengueCast BD

Probabilistic 1-4-week forecasts of dengue hospital admissions for Bangladesh
(national, 8 divisions, DNCC, DSCC), built entirely from public data, with a
pre-registered evaluation and a public, timestamped track record.

Not a clinical tool. Forecasts target admissions reported by DGHS, not infections.

## How the repository works

| Part | File | What it does |
| --- | --- | --- |
| Archive | `src/denguecast/archive.py` | Append-only store of every value as published; `get_data(as_of=t)` is the only way code reads data |
| Scraper | `src/denguecast/scrape.py` | Saves the DGHS dashboard daily, unchanged, with a SHA-256 hash |
| Probe | `src/denguecast/probe.py` | One-off check of DGHS, Mendeley and Open-Meteo access; writes `docs/probe_report.md` |
| Parser | `src/denguecast/release_parser.py` | Reads division counts from DGHS release text; flags incomplete reprints |
| Manual entry | `data/manual/daily_releases.csv` | Fallback: transcribe official releases with source URLs; rows that do not add up are rejected |
| Cleaning | `src/denguecast/cleaning.py` | Pre-registered rules 1-10 |
| Baselines | `src/denguecast/baselines.py` | Persistence (B1) and seasonal naive (B2) |
| Models | `src/denguecast/models.py` | Model A (LightGBM quantile), B3 (ARIMA family), ensemble; not yet trained on real data |
| Scoring | `src/denguecast/scoring.py` | WIS, coverage, relative WIS |
| Live forecast | `src/denguecast/live_forecast.py` | Builds and writes the weekly forecast; never overwrites |

## Rules the code enforces

- Test seasons 2024-2025 are locked: `get_data` refuses them unless `DENGUECAST_ALLOW_TEST_SEASONS=1`.
- Leakage test L10 (`tests/test_leakage.py`): a forecast from the full archive must equal one from an archive truncated at the forecast time.
- `scripts/check_append_only.py` fails CI if archive rows are edited or a published forecast changes.

## Schedules (GitHub Actions)

- `scrape`: daily 22:00 BDT, retry 09:00 BDT.
- `forecast`: Saturday 22:30 BDT; must be committed before Sunday 12:00 BDT.
- `probe`: run manually once to verify data access.

## Run locally

```
pip install -r requirements.txt
python -m pytest -q
```

See `docs/ASSUMPTIONS_AND_BLOCKERS.md` for what is verified, assumed and blocked,
and `docs/DEVIATIONS.md` for changes after the pre-registration is locked.

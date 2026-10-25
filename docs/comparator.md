# Comparator for the 2024 test (D6)

Rule (fixed before validation): the comparator is whichever of B1 (persistence) and B2 (seasonal naive)
has the lower mean WIS on the 2023 validation replay (count scale, forecasts produced by every model).

Source: `results/2023/summary.csv` (VALIDATION), run `python -m denguecast.evaluate --season 2023 --tune 20`.

| Model | Forecasts scored | Mean WIS (count) |
| --- | --- | --- |
| B1 persistence | 1710 | 442.087 |
| B2 seasonal naive | 1710 | 931.475 |

**Comparator: B1 persistence.** Recorded on 2026-10-25, before any 2024 data was ingested.

Model A hyperparameters for the 2024 run are fixed in `results/2023/model_a_params.json`
(Optuna TPE, seed 2026, 20 trials, D8).

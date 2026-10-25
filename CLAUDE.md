# CLAUDE.md — DengueCast BD

`DENGUECAST_GUIDE.md` is the single source of truth. Read it before working. Stop at every **GATE** and wait for the user.

## Rules

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

## Running

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; .venv/bin/python elsewhere
.venv/Scripts/python -m pytest -q
```

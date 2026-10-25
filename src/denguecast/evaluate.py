"""Forward-chaining replay, scoring and bootstrap (pre-registration Sections 8-9).

For each epi week W of a season, the forecast is made as of Saturday of W at
23:59 BDT (17:59 UTC) from ``live_forecast.weekly_series(as_of)``, so every
model sees exactly what was available then. Forecasts are scored against
``cleaning.final_truth_table`` (value as known 14 days after the target week).

Model A is refitted every 4 origins (D9) and predicts at the origins in
between with features up to each origin; B3 is refitted at every origin.

Test seasons (2024, 2025) are refused unless config.ALLOW_TEST_ENV is "1".

Usage:
    python -m denguecast.evaluate --season 2023
    python -m denguecast.evaluate --season 2023 --tune 20
    python -m denguecast.evaluate --season 2023 --model-a-params results/2023/model_a_params.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import archive, baselines, cleaning, config, live_forecast, models, scoring
from .epiweek import week_end

ALL_MODELS = ["persistence", "seasonal_naive", "model_a", "b3", "ensemble"]
MODEL_A_REFIT_EVERY = 4
RESULTS_DIR = config.REPO_ROOT / "results"
SCORE_KEYS = ["unit", "origin_week_end", "horizon"]


def season_origins(season: int) -> list[pd.Timestamp]:
    out, w = [], 1
    while True:
        try:
            end = week_end(season, w)
        except ValueError:
            break
        out.append(pd.Timestamp(end))
        w += 1
    return out


def as_of_for(origin) -> pd.Timestamp:
    """Saturday of the origin week at 23:59 BDT."""
    return pd.Timestamp(pd.Timestamp(origin).date(), tz="UTC") + pd.Timedelta(hours=17, minutes=59)


def _check_lock(season: int) -> bool:
    if season in config.TEST_SEASONS:
        if not config.test_seasons_unlocked():
            raise archive.SeasonLockError(f"season {season} is a locked test season; set {config.ALLOW_TEST_ENV}=1 only for the final run")
        return True
    return False


def histories(season: int, archive_file: Path | None = None, units=None) -> dict:
    """Weekly history as known at each origin of the season: {origin: DataFrame(unit, week_end, value)}.
    Origins without an observed NATIONAL value for that very week are left out."""
    include = _check_lock(season)
    units = units or config.BACKTEST_UNITS
    out = {}
    for origin in season_origins(season):
        as_of = as_of_for(origin)
        w = live_forecast.weekly_series(as_of, archive_file=archive_file, include_test_seasons=include)
        if live_forecast.latest_complete_origin(w, as_of) != origin:
            continue
        w = w[w["unit"].isin(units)]
        out[origin] = w[["unit", "week_end", "value_clipped"]].rename(columns={"value_clipped": "value"}).reset_index(drop=True)
    return out


def replay(season: int, model_names=ALL_MODELS, hist: dict | None = None, archive_file: Path | None = None,
           model_a_params: dict | None = None, early_stop_weeks: int | None = None) -> tuple[dict, dict]:
    """Run all models at every origin. Returns ({model: forecasts}, info)."""
    _check_lock(season)
    hist = hist if hist is not None else histories(season, archive_file)
    need = set(model_names) | ({"model_a", "b3"} if "ensemble" in model_names else set())
    fc = {m: [] for m in need | set(model_names)}
    info = {"origins": [str(o.date()) for o in hist], "not_produced": [], "model_a_fit_origins": []}
    fitted = None
    for i, (origin, h) in enumerate(hist.items()):
        made = {}
        for m in [x for x in ["persistence", "seasonal_naive", "model_a", "b3"] if x in need]:
            try:
                if m == "persistence":
                    f = baselines.persistence(h, origin, on_missing="skip")
                elif m == "seasonal_naive":
                    f = baselines.seasonal_naive(h, origin)
                elif m == "model_a":
                    if fitted is None or i % MODEL_A_REFIT_EVERY == 0:
                        fitted = models.fit_model_a(h, origin, params=model_a_params, early_stop_weeks=early_stop_weeks)
                        info["model_a_fit_origins"].append(str(origin.date()))
                    f = models.predict_model_a(fitted, h, origin)
                else:
                    f = models.b3_arima(h, origin)
                made[m] = f
                fc[m].append(f)
            except baselines.InsufficientHistory as exc:
                info["not_produced"].append({"model": m, "origin": str(origin.date()), "reason": str(exc)})
        if "ensemble" in model_names:
            if "model_a" in made and "b3" in made:
                fc["ensemble"].append(models.ensemble(made["model_a"], made["b3"]))
            else:
                info["not_produced"].append({"model": "ensemble", "origin": str(origin.date()), "reason": "a member is missing"})
    out = {m: (pd.concat(v, ignore_index=True) if v else pd.DataFrame(columns=baselines.FORECAST_COLS))
           for m, v in fc.items() if m in model_names}
    return out, info


def truth_for(season: int, origins, evaluated_at=None, archive_file: Path | None = None) -> pd.DataFrame:
    """Final truth for every season week and every target week of the given origins."""
    include = _check_lock(season)
    weeks = {(pd.Timestamp(o) + pd.Timedelta(weeks=h)).date() for o in origins for h in config.HORIZONS}
    weeks |= {o.date() for o in season_origins(season)}
    evaluated_at = evaluated_at or archive.utc_now()
    return cleaning.final_truth_table(config.BACKTEST_UNITS, sorted(weeks), "admissions", evaluated_at,
                                      archive_file=archive_file, include_test_seasons=include)


def phase_labels(truth: pd.DataFrame, season: int) -> pd.DataFrame:
    """Epidemic phase per (unit, week) of the season, from final truth (scoring only).
    Centred 3-week moving average, then the first rule that applies: peak (within
    2 weeks of the season maximum), low (< 10% of the maximum), growth (3-week
    growth > +10%), decline (< -10%), plateau."""
    t = truth.copy()
    t["week_end"] = pd.to_datetime(t["week_end"])
    season_weeks = {o for o in season_origins(season)}
    t = t[t["week_end"].isin(season_weeks)]
    out = []
    for u, g in t.groupby("unit"):
        s = g.set_index("week_end")["value"].sort_index()
        sm = s.rolling(3, center=True, min_periods=1).mean()
        mx = sm.max()
        peak_pos = int(np.nanargmax(sm.values)) if sm.notna().any() else -99
        for i, (wk, v) in enumerate(sm.items()):
            if pd.isna(v):
                ph = "unknown"
            elif abs(i - peak_pos) <= 2:
                ph = "peak"
            elif v < 0.10 * mx:
                ph = "low"
            else:
                prev = sm.iloc[i - 3] if i >= 3 else np.nan
                g3 = (v / prev - 1) if pd.notna(prev) and prev > 0 else np.nan
                ph = "growth" if g3 > 0.10 else "decline" if g3 < -0.10 else "plateau"
            out.append({"unit": u, "week_end": wk.date(), "phase": ph})
    return pd.DataFrame(out, columns=["unit", "week_end", "phase"])


def score_all(forecasts: dict, truth: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for m, f in forecasts.items():
        for scale, log in (("count", False), ("log1p", True)):
            s = scoring.score_forecasts(f, truth[["unit", "week_end", "value"]], log_scale=log)
            if not s.empty:
                rows.append(s.assign(model=m, scale=scale))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def common_keys(scores: pd.DataFrame, model_names) -> pd.DataFrame:
    """Forecast keys scored for every listed model (comparisons use only these)."""
    sets = [set(map(tuple, scores[(scores["model"] == m) & (scores["scale"] == "count")][SCORE_KEYS].astype(str).values))
            for m in model_names]
    keep = set.intersection(*sets) if sets else set()
    return pd.DataFrame(sorted(keep), columns=SCORE_KEYS)


def _restrict(scores: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    s = scores.copy()
    for c in SCORE_KEYS:
        s[c] = s[c].astype(str)
    return s.merge(keys, on=SCORE_KEYS)


def summarise(scores: pd.DataFrame, phases: pd.DataFrame, comparator: str | None) -> pd.DataFrame:
    s = scores.copy()
    ph = phases.assign(target_week_end=phases["week_end"].astype(str))[["unit", "target_week_end", "phase"]]
    s["target_week_end"] = s["target_week_end"].astype(str)
    s = s.merge(ph, on=["unit", "target_week_end"], how="left")
    s["phase"] = s["phase"].fillna("outside_season")
    rows = []
    for by in (None, "horizon", "unit", "phase"):
        groups = s.groupby(["model", "scale"] + ([by] if by else []))
        for key, g in groups:
            model, scale = key[0], key[1]
            row = {"breakdown": by or "all", "level": str(key[2]) if by else "all", "model": model, "scale": scale,
                   "n": len(g), "mean_wis": g["wis"].mean(), "mae": g["abs_error"].mean(),
                   "cov50": g["cov50"].mean(), "cov90": g["cov90"].mean()}
            if comparator:
                c = s[(s["model"] == comparator) & (s["scale"] == scale)]
                if by:
                    c = c[c[by] == key[2]]
                row["relative_wis"] = row["mean_wis"] / c["wis"].mean() if len(c) and c["wis"].mean() > 0 else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def bootstrap(scores_model: pd.DataFrame, scores_comparator: pd.DataFrame, block: int = 4,
              n_boot: int = 2000, seed: int = config.RANDOM_SEED) -> dict:
    """Relative WIS (model / comparator) with a moving-block bootstrap over origin
    weeks; all units and horizons of a week stay together."""
    m = scores_model[SCORE_KEYS + ["wis"]].astype({c: str for c in SCORE_KEYS}).merge(
        scores_comparator[SCORE_KEYS + ["wis"]].astype({c: str for c in SCORE_KEYS}), on=SCORE_KEYS, suffixes=("_m", "_c"))
    if m.empty:
        raise ValueError("no common scored forecasts")
    wk = m.groupby("origin_week_end")[["wis_m", "wis_c"]].sum().sort_index()
    a, b = wk["wis_m"].values, wk["wis_c"].values
    n = len(wk)
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    rel = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max(n - block + 1, 1), size=n_blocks)
        idx = np.concatenate([np.arange(s, min(s + block, n)) for s in starts])[:n]
        rel[i] = a[idx].sum() / b[idx].sum()
    lo, hi = np.percentile(rel, [2.5, 97.5])
    return {"relative_wis": float(a.sum() / b.sum()), "lower95": float(lo), "upper95": float(hi),
            "n_weeks": int(n), "n_forecasts": int(len(m)), "block": block, "n_boot": n_boot, "seed": seed}


def tune_model_a(season: int, n_trials: int, hist: dict, truth: pd.DataFrame, log=print) -> dict:
    """Optuna TPE (seed 2026) over the pre-registered space; objective = mean
    count-scale WIS of Model A over the season. Early stopping: 100 rounds on
    the last 8 weeks of each training window, up to 2,000 trees."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = dict(learning_rate=trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
                      num_leaves=trial.suggest_int("num_leaves", 8, 64),
                      min_data_in_leaf=trial.suggest_int("min_data_in_leaf", 10, 100),
                      feature_fraction=trial.suggest_float("feature_fraction", 0.6, 1.0),
                      lambda_l2=trial.suggest_float("lambda_l2", 0.0, 10.0), n_estimators=2000)
        t0 = time.time()
        try:
            fc, _ = replay(season, ["model_a"], hist=hist, model_a_params=params, early_stop_weeks=8)
        except baselines.InsufficientHistory:
            return float("inf")
        s = scoring.score_forecasts(fc["model_a"], truth[["unit", "week_end", "value"]])
        val = float(s["wis"].mean())
        log(f"  trial {trial.number}: mean WIS {val:.3f} ({time.time() - t0:.0f}s) {params}")
        return val

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=config.RANDOM_SEED))
    study.optimize(objective, n_trials=n_trials)
    best = {**study.best_params, "n_estimators": 2000}
    return {"best_params": best, "early_stop_weeks": 8, "best_mean_wis": study.best_value,
            "trials": [{"number": t.number, "value": t.value, "params": t.params} for t in study.trials]}


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=config.REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--models", nargs="+", default=ALL_MODELS)
    ap.add_argument("--tune", type=int, default=0, help="Optuna trials for Model A before the replay (max 20, D8)")
    ap.add_argument("--model-a-params", default=None, help="JSON file with tuned Model A params")
    ap.add_argument("--comparator", default=None, help="comparator model for relative WIS (default: from docs/comparator.md rule)")
    args = ap.parse_args(argv)
    if args.tune > 20:
        raise SystemExit("D8: at most 20 Optuna trials")
    out_dir = RESULTS_DIR / str(args.season)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = archive.utc_now()
    print(f"Replay season {args.season}: building weekly histories as known at each origin ...", flush=True)
    hist = histories(args.season)
    print(f"  {len(hist)} origins", flush=True)
    truth = truth_for(args.season, list(hist))
    params, es = None, None
    if args.tune:
        print(f"Tuning Model A: {args.tune} trials", flush=True)
        tuned = tune_model_a(args.season, args.tune, hist, truth)
        (out_dir / "model_a_tuning.json").write_text(json.dumps(tuned, indent=2, default=str), encoding="utf-8")
        params, es = tuned["best_params"], tuned["early_stop_weeks"]
        (out_dir / "model_a_params.json").write_text(json.dumps({"params": params, "early_stop_weeks": es}, indent=2), encoding="utf-8")
    elif args.model_a_params:
        p = json.loads(Path(args.model_a_params).read_text(encoding="utf-8"))
        params, es = p["params"], p.get("early_stop_weeks")
    print("Running models ...", flush=True)
    fc, info = replay(args.season, args.models, hist=hist, model_a_params=params, early_stop_weeks=es)
    for m, f in fc.items():
        f.to_csv(out_dir / f"forecasts_{m}.csv", index=False)
    scores = score_all(fc, truth)
    keys = common_keys(scores, list(fc))
    scored = _restrict(scores, keys)
    scored.to_csv(out_dir / "scores.csv", index=False)
    phases = phase_labels(truth, args.season)
    phases.to_csv(out_dir / "phases.csv", index=False)
    truth.to_csv(out_dir / "truth.csv", index=False)
    comparator = args.comparator
    if comparator is None and {"persistence", "seasonal_naive"} <= set(fc):
        c = scored[scored["scale"] == "count"].groupby("model")["wis"].mean()
        comparator = "persistence" if c["persistence"] <= c["seasonal_naive"] else "seasonal_naive"
    summary = summarise(scored, phases, comparator)
    summary.to_csv(out_dir / "summary.csv", index=False)
    boot = {}
    if comparator:
        for m in fc:
            if m == comparator:
                continue
            for scale in ("count", "log1p"):
                sm = scored[(scored["model"] == m) & (scored["scale"] == scale)]
                sc = scored[(scored["model"] == comparator) & (scored["scale"] == scale)]
                for label, hz in (("h1-3", [1, 2, 3]), ("h4", [4])):
                    boot[f"{m}|{scale}|{label}"] = bootstrap(sm[sm["horizon"].astype(int).isin(hz)],
                                                             sc[sc["horizon"].astype(int).isin(hz)])
    n_fc = {m: int(f.groupby(SCORE_KEYS).ngroups) for m, f in fc.items()}
    meta = {"season": args.season, "label": "VALIDATION" if args.season in config.VALIDATION_SEASONS else "TEST" if args.season in config.TEST_SEASONS else "OTHER",
            "command": "python -m denguecast.evaluate " + " ".join(argv if argv is not None else sys.argv[1:]),
            "code_commit": _git_sha(), "started_utc": started.isoformat(), "finished_utc": archive.utc_now().isoformat(),
            "comparator": comparator, "model_a_params": params, "early_stop_weeks": es,
            "forecasts_made": n_fc, "forecasts_scored_common": int(len(keys)),
            "truth_missing_target_weeks": sorted({str(w) for w in truth.loc[truth["value"].isna(), "week_end"]}),
            "bootstrap": boot, **info}
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    print(summary[(summary["breakdown"].isin(["all", "horizon"]))].to_string(index=False))
    print(json.dumps({k: v for k, v in meta.items() if k in ("label", "comparator", "forecasts_made", "forecasts_scored_common")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

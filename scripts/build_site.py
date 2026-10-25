"""Build the dashboard site/index.html (guide Section 9).

Every number on the page is read from files in forecasts/ or results/ and
embedded as JSON; charts are drawn in the browser from that JSON with inline
SVG. The page is a single self-contained file and makes no external requests.

Usage:  python scripts/build_site.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FORECASTS, RESULTS, SITE = ROOT / "forecasts", ROOT / "results", ROOT / "site"
TEMPLATE = Path(__file__).with_name("site_template.html")
REPO = "https://github.com/rashed-ahammod/denguecast-bd"
sys.path.insert(0, str(Path(__file__).parent))
from write_results import h1_verdict, h2_verdict  # noqa: E402

UNIT_NAMES = {
    "NATIONAL": "Bangladesh (national)",
    "DHAKA_DIV_TOTAL": "Dhaka division (incl. city corporations)",
    "DHAKA_DIV": "Dhaka division (outside city corporations)",
    "DNCC": "Dhaka North City Corporation",
    "DSCC": "Dhaka South City Corporation",
    "DHAKA_CITY": "Dhaka city corporations (combined)",
    "CHATTOGRAM_DIV": "Chattogram division",
    "BARISHAL_DIV": "Barishal division",
    "KHULNA_DIV": "Khulna division",
    "RAJSHAHI_DIV": "Rajshahi division",
    "RANGPUR_DIV": "Rangpur division",
    "MYMENSINGH_DIV": "Mymensingh division",
    "SYLHET_DIV": "Sylhet division",
}
UNIT_ORDER = list(UNIT_NAMES)
MODEL_NAMES = {"ensemble": "Ensemble (Model A + B3)", "b3": "B3: ARIMA", "model_a": "Model A: LightGBM",
               "persistence": "B1: Persistence", "seasonal_naive": "B2: Seasonal naive"}
BAND_QS = [0.05, 0.25, 0.5, 0.75, 0.95]


def _r(v, d=1):
    return None if v is None or pd.isna(v) else round(float(v), d)


def _uorder(units):
    return sorted(units, key=lambda u: UNIT_ORDER.index(u) if u in UNIT_ORDER else 99)


def live() -> dict | None:
    metas = sorted(FORECASTS.glob("*/*.json"))
    if not metas:
        return None
    meta_path = metas[-1]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fc = pd.read_csv(meta_path.with_suffix(".csv"))
    hist_path = meta_path.with_name(meta_path.stem + "_history.csv")
    hist = pd.read_csv(hist_path) if hist_path.exists() else pd.DataFrame(columns=["unit", "week_end", "value"])
    units = {}
    for u in _uorder(fc["unit"].unique()):
        g = fc[fc["unit"] == u]
        h = hist[(hist["unit"] == u) & hist["value"].notna()]
        units[u] = {
            "history": [[str(w), _r(v, 0)] for w, v in zip(h["week_end"], h["value"])],
            "forecast": [{"h": int(hz), "week": str(gg["target_week_end"].iloc[0]),
                          **{f"q{int(q * 1000)}": _r(gg.loc[gg["quantile"] == q, "value"].iloc[0], 0) for q in [0.025, *BAND_QS, 0.975]}}
                         for hz, gg in g.groupby("horizon")],
        }
    return {"meta": meta, "units": units, "files": {
        "csv": f"{REPO}/blob/main/{meta_path.with_suffix('.csv').relative_to(ROOT).as_posix()}",
        "json": f"{REPO}/blob/main/{meta_path.relative_to(ROOT).as_posix()}"}}


def season(season: int) -> dict | None:
    d = RESULTS / str(season)
    if not (d / "run_meta.json").exists():
        return None
    meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
    summ = pd.read_csv(d / "summary.csv")
    scores = pd.read_csv(d / "scores.csv")
    truth = pd.read_csv(d / "truth.csv")
    truth_map = {(u, str(w)): v for u, w, v in zip(truth["unit"], truth["week_end"], truth["value"])}
    phases = pd.read_csv(d / "phases.csv")
    phase_map = {(u, str(w)): p for u, w, p in zip(phases["unit"], phases["week_end"], phases["phase"])}
    ens = pd.read_csv(d / "forecasts_ensemble.csv")
    per = pd.read_csv(d / "forecasts_persistence.csv")
    ens = ens[ens["quantile"].round(3).isin(BAND_QS)]
    ew = ens.pivot_table(index=["unit", "horizon", "target_week_end"], columns="quantile", values="value").reset_index()
    pm = per[per["quantile"] == 0.5].set_index(["unit", "horizon", "target_week_end"])["value"]
    track = {}
    for (u, hz), g in ew.groupby(["unit", "horizon"]):
        rows = []
        for r in g.sort_values("target_week_end").itertuples(index=False):
            w = str(r.target_week_end)
            rows.append([w, *[_r(getattr(r, f"_{i + 3}"), 0) for i in range(len(BAND_QS))],
                         _r(pm.get((u, hz, r.target_week_end)), 0), _r(truth_map.get((u, w)), 0), phase_map.get((u, w), "")])
        track.setdefault(u, {})[str(int(hz))] = rows
    count = summ[summ["scale"] == "count"]
    by_h = count[count["breakdown"] == "horizon"]
    models = {}
    for m in MODEL_NAMES:
        sub = by_h[by_h["model"] == m]
        if sub.empty:
            continue
        b = meta["bootstrap"].get(f"{m}|count|h1-3")
        bl = meta["bootstrap"].get(f"{m}|log1p|h1-3")
        models[m] = {"name": MODEL_NAMES[m],
                     "by_h": {str(int(r.level)): {"wis": _r(r.mean_wis), "rel": _r(r.relative_wis, 3), "cov50": _r(r.cov50, 3),
                                                  "cov90": _r(r.cov90, 3), "n": int(r.n)} for r in sub.itertuples()},
                     "rel13": _r(b["relative_wis"], 3) if b else 1.0, "lo13": _r(b["lower95"], 3) if b else None,
                     "hi13": _r(b["upper95"], 3) if b else None,
                     "rel13_log": _r(bl["relative_wis"], 3) if bl else 1.0}
    e13 = scores[(scores["model"] == "ensemble") & (scores["scale"] == "count") & (scores["horizon"].isin([1, 2, 3]))]
    b = meta["bootstrap"].get("ensemble|count|h1-3")
    verdicts = None
    if b is not None and len(e13):
        verdicts = {"h1": h1_verdict(b), "h1_rel": _r(b["relative_wis"], 3), "h1_lo": _r(b["lower95"], 3), "h1_hi": _r(b["upper95"], 3),
                    "h2": h2_verdict(e13["cov50"].mean(), e13["cov90"].mean()),
                    "cov50": _r(e13["cov50"].mean(), 3), "cov90": _r(e13["cov90"].mean(), 3)}
    ph = count[(count["breakdown"] == "phase") & count["model"].isin(["ensemble"])]
    phases_out = [{"phase": r.level, "n": int(r.n), "rel": _r(r.relative_wis, 3), "cov50": _r(r.cov50, 3), "cov90": _r(r.cov90, 3)}
                  for r in ph.itertuples() if r.level != "outside_season"]
    by_u = count[(count["breakdown"] == "unit") & (count["model"] == "ensemble")]
    units_out = [{"unit": r.level, "rel": _r(r.relative_wis, 3), "wis": _r(r.mean_wis), "cov90": _r(r.cov90, 3)}
                 for r in by_u.itertuples()]
    return {"season": season, "label": meta["label"], "comparator": meta["comparator"], "commit": meta["code_commit"],
            "command": meta["command"], "finished": meta["finished_utc"], "n_scored": meta["forecasts_scored_common"],
            "truth_missing": meta["truth_missing_target_weeks"], "units": _uorder(track), "track": track,
            "models": models, "verdicts": verdicts, "phases": phases_out, "by_unit": _uorder_rows(units_out)}


def _uorder_rows(rows):
    return sorted(rows, key=lambda r: UNIT_ORDER.index(r["unit"]) if r["unit"] in UNIT_ORDER else 99)


def quality() -> dict | None:
    p = RESULTS / "data_report" / "weekly_2022_2023.csv"
    if not p.exists():
        return None
    w = pd.read_csv(p)
    flags = w["flag"].astype(object).fillna("")
    return {"units": int(w["unit"].nunique()), "unit_weeks": int(len(w)), "recovered": int((flags == "recovered").sum()),
            "missing": int(w["value"].isna().sum()), "outliers": int(w["outlier"].sum())}


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    data = {"repo": REPO, "unit_names": UNIT_NAMES, "live": live(), "test": season(2024), "validation": season(2023),
            "quality": quality()}
    payload = json.dumps(data, separators=(",", ":"), default=str).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
    (SITE / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {SITE / 'index.html'} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()

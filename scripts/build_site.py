"""Build the static dashboard site/index.html (guide Section 9).

Every number on the page is read from files in forecasts/ or results/.
Charts are matplotlib PNGs embedded as base64; the page makes no external requests.

Usage:  python scripts/build_site.py
"""
from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FORECASTS, RESULTS, SITE = ROOT / "forecasts", ROOT / "results", ROOT / "site"
BACKTEST_UNITS = ["NATIONAL", "DHAKA_DIV_TOTAL", "CHATTOGRAM_DIV", "BARISHAL_DIV"]
LIMITATIONS = [
    "Targets are hospital admissions reported by DGHS, not infections.",
    "Only one season (2024) is a true test; 2023 results are validation and therefore optimistic.",
    "The 2022-2024 data (Mendeley z5mvwrfgsz) has no separate Dhaka city corporations and no national series; "
    "national values in the backtest are the sum of the eight divisions (amendment D10).",
    "Weather and population features are not used yet.",
    "Reporting coverage has changed over time; serotype shifts and immunity are not in public data.",
    "Division level is too coarse to target mosquito control within cities.",
    "Live forecasts cannot be scored yet; no claim of live accuracy is made.",
    "The first live forecast (origin 24 Oct 2026) was published late; see docs/DEVIATIONS.md.",
]
COLORS = {"obs": "#1f2937", "med": "#2563eb", "b90": "#bfdbfe", "b50": "#93c5fd"}


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _bands(ax, fc: pd.DataFrame, x_col: str):
    w = fc.pivot_table(index=x_col, columns="quantile", values="value").sort_index()
    x = pd.to_datetime(w.index)
    ax.fill_between(x, w[0.05], w[0.95], color=COLORS["b90"], label="90% interval")
    ax.fill_between(x, w[0.25], w[0.75], color=COLORS["b50"], label="50% interval")
    ax.plot(x, w[0.5], color=COLORS["med"], marker="o", ms=3, label="median forecast")


def latest_live() -> str:
    metas = sorted(FORECASTS.glob("*/*.json"))
    if not metas:
        return "<p>No live forecast has been published yet.</p>"
    meta_path = metas[-1]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fc = pd.read_csv(meta_path.with_suffix(".csv"))
    hist_path = meta_path.with_name(meta_path.stem + "_history.csv")
    hist = pd.read_csv(hist_path) if hist_path.exists() else pd.DataFrame(columns=["unit", "week_end", "value"])
    parts = [f"<p>Model <b>{html.escape(meta['model'])}</b>, origin week ending <b>{meta['origin_week_end']}</b>, "
             f"created {html.escape(meta.get('created_at_bdt', '?'))} (BDT), code commit <code>{meta.get('code_commit', '?')[:10]}</code>, "
             f"late: <b>{meta.get('late')}</b>. Source files: <code>{meta_path.relative_to(ROOT).as_posix()}</code> and .csv.</p>"]
    if meta.get("units_skipped"):
        parts.append(f"<p>Units without a value at the origin (not forecast): {', '.join(meta['units_skipped'])}.</p>")
    imgs = []
    for unit, g in fc.groupby("unit"):
        fig, ax = plt.subplots(figsize=(4.2, 2.6))
        h = hist[hist["unit"] == unit].tail(12)
        if len(h):
            ax.plot(pd.to_datetime(h["week_end"]), h["value"], color=COLORS["obs"], marker="o", ms=3, label="observed")
        _bands(ax, g, "target_week_end")
        ax.set_title(unit, fontsize=9)
        ax.tick_params(labelsize=7)
        ax.set_ylim(bottom=0)
        fig.autofmt_xdate()
        imgs.append(f'<figure><img alt="{unit} live forecast" src="{_png(fig)}"></figure>')
    parts.append('<div class="grid">' + "".join(imgs) + "</div>")
    return "".join(parts)


def backtest(season: int) -> str:
    d = RESULTS / str(season)
    if not (d / "summary.csv").exists():
        return f"<p>The {season} backtest has not been run yet.</p>"
    meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
    summ = pd.read_csv(d / "summary.csv")
    label = meta.get("label", "")
    out = [f"<p><b>{label}</b> season {season}. Comparator: <b>{meta.get('comparator')}</b>. "
           f"Command <code>{html.escape(meta['command'])}</code> at commit <code>{meta['code_commit'][:10]}</code>. "
           f"Forecasts scored (common to all models): {meta['forecasts_scored_common']}.</p>"]
    tab = summ[summ["breakdown"].isin(["all", "horizon"]) & (summ["scale"] == "count")]
    tab = tab[["level", "model", "n", "mean_wis", "relative_wis", "cov50", "cov90"]].rename(columns={"level": "horizon"})
    out.append(tab.to_html(index=False, float_format=lambda v: f"{v:.3f}", classes="tbl"))
    ens = d / "forecasts_ensemble.csv"
    truth = pd.read_csv(d / "truth.csv")
    if ens.exists():
        fc = pd.read_csv(ens)
        fc = fc[fc["horizon"] == 1]
        imgs = []
        for unit in BACKTEST_UNITS:
            g = fc[fc["unit"] == unit]
            if g.empty:
                continue
            fig, ax = plt.subplots(figsize=(4.2, 2.6))
            _bands(ax, g, "target_week_end")
            t = truth[(truth["unit"] == unit) & truth["week_end"].isin(g["target_week_end"].unique())].sort_values("week_end")
            ax.plot(pd.to_datetime(t["week_end"]), t["value"], color=COLORS["obs"], lw=1, label="truth")
            ax.set_title(f"{unit}: ensemble, 1 week ahead", fontsize=9)
            ax.tick_params(labelsize=7)
            fig.autofmt_xdate()
            imgs.append(f'<figure><img alt="{unit} backtest" src="{_png(fig)}"></figure>')
        out.append('<div class="grid">' + "".join(imgs) + "</div>")
    return "".join(out)


def data_quality() -> str:
    p = RESULTS / "data_report" / "weekly_2022_2023.csv"
    if not p.exists():
        return "<p>No data report yet.</p>"
    w = pd.read_csv(p)
    flags = w["flag"].astype(object).fillna("")
    return (f"<p>2022-2023 weekly series ({w['unit'].nunique()} units, {len(w)} unit-weeks): "
            f"recovered {int((flags == 'recovered').sum())}, missing {int(w['value'].isna().sum())}, "
            f"flagged as outliers (rule 9) {int(w['outlier'].sum())}. Source: <code>{p.relative_to(ROOT).as_posix()}</code>.</p>")


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    sections = [
        ("Latest live forecast", latest_live()),
        ("Backtest: 2024 test season", backtest(2024)),
        ("Validation: 2023 (optimistic; used for tuning and choosing the comparator)", backtest(2023)),
        ("Data quality", data_quality()),
        ("Limitations", "<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in LIMITATIONS) + "</ul>"),
    ]
    body = "".join(f"<section><h2>{html.escape(t)}</h2>{c}</section>" for t, c in sections)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>DengueCast BD</title>
<style>
:root{{--bg:#fff;--fg:#111827;--muted:#4b5563;--line:#e5e7eb}}
@media (prefers-color-scheme: dark){{:root{{--bg:#0b1220;--fg:#e5e7eb;--muted:#9ca3af;--line:#1f2937}} img{{background:#fff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:16px}} h1{{margin:.2em 0}} .sub{{color:var(--muted)}}
section{{border-top:1px solid var(--line);padding:8px 0}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px}}
figure{{margin:0}} img{{max-width:100%;height:auto;border-radius:4px}}
.tbl{{border-collapse:collapse;font-size:13px;display:block;overflow-x:auto}} .tbl td,.tbl th{{border:1px solid var(--line);padding:2px 6px;text-align:right}}
code{{font-size:12px}}
</style></head><body><main>
<h1>DengueCast BD</h1>
<p class="sub">Probabilistic forecasts of weekly dengue hospital admissions in Bangladesh, 1-4 weeks ahead, from public data,
evaluated under a pre-registration. Not a clinical tool. Data: DGHS; Mendeley z5mvwrfgsz v1 (Naher 2026, CC BY 4.0).</p>
{body}
</main></body></html>"""
    (SITE / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {SITE / 'index.html'} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()

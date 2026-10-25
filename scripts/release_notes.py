"""Release notes for one published forecast (used by .github/workflows/release.yml).

GitHub emails everyone who watches the repository's releases, so each new
forecast reaches subscribers without a server. Numbers are read from the
forecast files only.

Usage:  python scripts/release_notes.py forecasts/<origin>/<model>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build_site import SITE_URL, UNIT_NAMES, _uorder  # noqa: E402


def notes(meta_path: Path) -> str:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fc = pd.read_csv(meta_path.with_suffix(".csv"))
    h1 = fc[fc["horizon"] == 1]
    week1 = h1["target_week_end"].iloc[0]
    rows = []
    for u in _uorder(h1["unit"].unique()):
        q = h1[h1["unit"] == u].set_index("quantile")["value"]
        q4 = fc[(fc["unit"] == u) & (fc["horizon"] == 4)].set_index("quantile")["value"]
        rows.append(f"| {UNIT_NAMES.get(u, u)} | {q[0.5]:,.0f} | {q[0.25]:,.0f}–{q[0.75]:,.0f} | {q[0.95]:,.0f} | {q4[0.95]:,.0f} |")
    nat = h1[h1["unit"] == "NATIONAL"].set_index("quantile")["value"]
    lines = [
        f"**Next week (to {week1}): Bangladesh can expect about {nat[0.5]:,.0f} dengue hospital admissions** "
        f"(likely {nat[0.25]:,.0f}–{nat[0.75]:,.0f}; very likely {nat[0.05]:,.0f}–{nat[0.95]:,.0f}).",
        "",
        "| Area | Next week, middle | Likely (50%) | Prepare for up to (next week) | Prepare for up to (in 4 weeks) |",
        "| --- | ---: | ---: | ---: | ---: |",
        *rows,
        "",
        f"Not forecast this week (incomplete DGHS data): {', '.join(UNIT_NAMES.get(u, u) for u in meta.get('units_skipped', [])) or 'none'}.",
        f"Model: {meta['model']}. Created {meta['created_at_bdt']} (BDT)" + (" — **published late**." if meta.get("late") else "."),
        "",
        f"Alerts, Bangla message and charts: {SITE_URL}#alerts",
        "",
        "Planning aid built from public DGHS data; not an official DGHS warning. / সরকারি DGHS তথ্য থেকে তৈরি পরিকল্পনা-সহায়ক পূর্বাভাস; আনুষ্ঠানিক সতর্কবার্তা নয়।",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes(Path(sys.argv[1])), end="")

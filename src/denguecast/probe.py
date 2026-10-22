"""Data-access probe, run from GitHub Actions (which has open internet).

It verifies, and records evidence for, three things the sandbox could not:
  1. Can the DGHS dashboard be downloaded, and how does it deliver its data?
  2. Can the Mendeley 2022-2024 dataset files be listed and downloaded?
  3. Is the Open-Meteo historical weather API reachable?
Everything downloaded is stored raw via archive.save_raw_snapshot. Results are
written to docs/probe_report.md. Nothing is parsed into the archive here.

Usage:  python -m denguecast.probe
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import requests

from . import archive, config
from .scrape import DASHBOARD_URL, USER_AGENT

MENDELEY_DATASETS = {
    # id: (version, description)
    "z5mvwrfgsz": (1, "Division-wise daily dengue cases with weather, 2022-2024"),
    "cgwjshkx5k": (2, "Monthly division-level dengue cases, 2020-2025"),
}
# Candidate public endpoints; the probe records which ones work.
MENDELEY_ENDPOINTS = [
    "https://data.mendeley.com/public-api/datasets/{id}",
    "https://data.mendeley.com/public-api/datasets/{id}/files?folder_id=root&version={v}",
]
OPEN_METEO_TEST = (
    "https://archive-api.open-meteo.com/v1/archive?latitude=23.78&longitude=90.40"
    "&start_date=2022-07-01&end_date=2022-07-07&daily=temperature_2m_mean,precipitation_sum"
    "&timezone=Asia%2FDhaka"
)
REPORT = config.REPO_ROOT / "docs" / "probe_report.md"
MAX_DOWNLOAD_BYTES = 50_000_000


def _get(url: str) -> requests.Response:
    return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=90)


def probe_dashboard(lines: list[str]) -> None:
    lines.append("## 1. DGHS dashboard\n")
    try:
        r = _get(DASHBOARD_URL)
    except requests.RequestException as exc:
        lines.append(f"- FAILED to download: `{exc}`\n")
        return
    lines.append(f"- HTTP {r.status_code}, {len(r.content):,} bytes, content-type `{r.headers.get('content-type')}`")
    digest, path = archive.save_raw_snapshot(r.content, "dghs_dashboard", DASHBOARD_URL, "html")
    lines.append(f"- Raw page stored: `{path}` (sha256 {digest[:12]})")
    html = r.text
    scripts = re.findall(r"<script[^>]*src=[\"']([^\"']+)", html, flags=re.I)
    lines.append(f"- External scripts ({len(scripts)}): " + ", ".join(f"`{s}`" for s in scripts[:30]))
    libs = [lib for lib in ("Highcharts", "Chart(", "echarts", "plotly", "google.visualization", "ApexCharts") if lib in html]
    lines.append(f"- Chart libraries mentioned in page: {libs or 'none found'}")
    endpoints = sorted(set(re.findall(r"[\"']([^\"'\s]+\.(?:php|json|pdf|csv|xlsx)(?:\?[^\"'\s]*)?)[\"']", html)))
    lines.append(f"- Linked .php/.json/.pdf/.csv/.xlsx URLs ({len(endpoints)}):")
    lines.extend(f"    - `{e}`" for e in endpoints[:60])
    ajax = re.findall(r"(?:\$\.ajax|\$\.get|\$\.post|fetch\()\s*\(?\s*[\"'{][^\n]{0,160}", html)
    lines.append(f"- AJAX/fetch calls found: {len(ajax)}")
    lines.extend(f"    - `{a.strip()[:160]}`" for a in ajax[:20])
    data_arrays = re.findall(r"data\s*:\s*\[[^\]]{0,200}", html)
    lines.append(f"- Inline `data: [...]` arrays found: {len(data_arrays)} (first 5 shown, truncated)")
    lines.extend(f"    - `{d[:200]}`" for d in data_arrays[:5])
    lines.append("")


def probe_mendeley(lines: list[str]) -> None:
    lines.append("## 2. Mendeley datasets\n")
    for ds_id, (version, desc) in MENDELEY_DATASETS.items():
        lines.append(f"### {ds_id} (v{version}): {desc}\n")
        page = f"https://data.mendeley.com/datasets/{ds_id}/{version}"
        try:
            r = _get(page)
            lines.append(f"- Dataset page: HTTP {r.status_code}, {len(r.content):,} bytes")
            archive.save_raw_snapshot(r.content, f"mendeley_{ds_id}_page", page, "html")
        except requests.RequestException as exc:
            lines.append(f"- Dataset page FAILED: `{exc}`")
        for tmpl in MENDELEY_ENDPOINTS:
            url = tmpl.format(id=ds_id, v=version)
            try:
                r = _get(url)
            except requests.RequestException as exc:
                lines.append(f"- `{url}` FAILED: `{exc}`")
                continue
            lines.append(f"- `{url}` -> HTTP {r.status_code}, {len(r.content):,} bytes")
            if r.status_code != 200:
                continue
            archive.save_raw_snapshot(r.content, f"mendeley_{ds_id}_api", url, "json")
            try:
                payload = r.json()
            except ValueError:
                lines.append("    - not JSON")
                continue
            files = payload if isinstance(payload, list) else payload.get("files", [])
            for f in files if isinstance(files, list) else []:
                name = f.get("filename") or f.get("name")
                size = (f.get("content_details") or {}).get("size") or f.get("size")
                dl = (f.get("content_details") or {}).get("download_url") or f.get("download_url")
                lines.append(f"    - file `{name}` size={size} download_url={'yes' if dl else 'no'}")
                if dl and (size is None or int(size) <= MAX_DOWNLOAD_BYTES):
                    try:
                        fr = _get(dl)
                        ext = (name or "bin").rsplit(".", 1)[-1]
                        _, p = archive.save_raw_snapshot(fr.content, f"mendeley_{ds_id}_files", dl, ext)
                        lines.append(f"        - downloaded -> `{p}` (HTTP {fr.status_code})")
                    except requests.RequestException as exc:
                        lines.append(f"        - download FAILED: `{exc}`")
            if isinstance(payload, dict):
                lic = payload.get("data_licence") or payload.get("license")
                if lic:
                    lines.append(f"    - licence field: `{json.dumps(lic)[:200]}`")
        lines.append("")


def probe_open_meteo(lines: list[str]) -> None:
    lines.append("## 3. Open-Meteo historical weather\n")
    try:
        r = _get(OPEN_METEO_TEST)
        lines.append(f"- HTTP {r.status_code}, {len(r.content):,} bytes")
        if r.ok:
            archive.save_raw_snapshot(r.content, "open_meteo_probe", OPEN_METEO_TEST, "json")
            daily = r.json().get("daily", {})
            lines.append(f"- Variables returned: {list(daily.keys())}; days: {len(daily.get('time', []))}")
    except requests.RequestException as exc:
        lines.append(f"- FAILED: `{exc}`")
    lines.append("")


def main() -> int:
    lines = [
        "# Data-access probe report",
        "",
        f"Run at {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} by `python -m denguecast.probe`.",
        "Raw responses are stored under `data/raw/` and logged in `data/archive/raw_manifest.csv`.",
        "",
    ]
    probe_dashboard(lines)
    probe_mendeley(lines)
    probe_open_meteo(lines)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

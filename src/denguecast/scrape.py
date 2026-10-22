"""Daily DGHS dashboard scraper.

Step 1 (always): download the dashboard page and store it unchanged with a
retrieval timestamp and SHA-256 hash (pre-registration Section 4). Raw
snapshots are the true vintage record: they can be re-parsed later with
``available_at = retrieved_at``.

Step 2 (only when verified): parse values into the archive. No parser for the
division tables is enabled yet because the dashboard's raw HTML has not been
inspected (blocker B2 in docs/ASSUMPTIONS_AND_BLOCKERS.md). Until then this
script stores raw pages only and exits successfully.

Usage:  python -m denguecast.scrape
"""
from __future__ import annotations

import re
import sys
from datetime import datetime

import requests

from . import archive

DASHBOARD_URL = "https://dashboard.dghs.gov.bd/pages/heoc_dengue_v1.php"
USER_AGENT = "DengueCastBD-research-archiver/0.1 (+public GitHub repository; contact in README)"
TIMEOUT = 60


def fetch(url: str) -> bytes:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.content


def parse_last_updated(html: str) -> datetime | None:
    """'Last Updated: 12-Apr-2026' -> date. Used only to check freshness."""
    m = re.search(r"Last\s+Updated:\s*(\d{1,2}-[A-Za-z]{3}-\d{4})", html)
    return datetime.strptime(m.group(1), "%d-%b-%Y") if m else None


def main() -> int:
    retrieved_at = archive.utc_now()
    try:
        content = fetch(DASHBOARD_URL)
    except requests.RequestException as exc:
        print(f"ERROR: could not fetch {DASHBOARD_URL}: {exc}", file=sys.stderr)
        return 1
    digest, path = archive.save_raw_snapshot(
        content, source="dghs_dashboard", url=DASHBOARD_URL, extension="html", retrieved_at=retrieved_at
    )
    html = content.decode("utf-8", errors="replace")
    last_updated = parse_last_updated(html)
    print(f"Saved {path} sha256={digest[:12]} last_updated={last_updated.date() if last_updated else 'NOT FOUND'}")
    print("Division-table parser not enabled yet (blocker B2); raw snapshot stored only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

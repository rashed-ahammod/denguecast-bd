"""Fail if a commit edits earlier archive rows or changes a published forecast.

Usage:  python scripts/check_append_only.py <base-git-ref>
Checks, between <base> and the working tree:
- data/archive/observations.csv, data/archive/raw_manifest.csv and
  data/quality_log.csv may only have lines appended;
- files under forecasts/ and data/raw/ may only be added, never modified or deleted.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APPEND_ONLY = ["data/archive/observations.csv", "data/archive/raw_manifest.csv", "data/quality_log.csv"]
ADD_ONLY_DIRS = ["forecasts/", "data/raw/"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def main(base: str) -> int:
    if set(base) == {"0"} or git("cat-file", "-e", f"{base}^{{commit}}").returncode != 0:
        print(f"Base ref {base!r} not available (new branch or first push); skipping.")
        return 0
    errors = []
    for f in APPEND_ONLY:
        old = git("show", f"{base}:{f}")
        if old.returncode != 0:
            continue  # file did not exist at base
        new = Path(f).read_text(encoding="utf-8") if Path(f).exists() else ""
        if not new.startswith(old.stdout):
            errors.append(f"{f}: existing content was modified or removed (only appends allowed)")
    diff = git("diff", "--name-status", base, "--", *ADD_ONLY_DIRS)
    for line in diff.stdout.splitlines():
        status, *paths = line.split("\t")
        if not status.startswith("A") and not paths[-1].endswith(".gitkeep"):
            errors.append(f"{paths[-1]}: status {status} (files here may only be added)")
    for e in errors:
        print(f"APPEND-ONLY VIOLATION: {e}", file=sys.stderr)
    print("Append-only check passed." if not errors else f"{len(errors)} violation(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "HEAD~1"))

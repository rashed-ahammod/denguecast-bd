"""Append-only observation archive and the single as-of data access point.

Rules enforced here (pre-registration Sections 4 and 6):
- Rows are only ever appended. A correction is a new row, never an edit.
- Every row records when it became available (``available_at``, UTC).
- All modelling code reads data through ``get_data(as_of=t)`` (rule L1), which
  returns only rows available at or before t and, for each key, the latest
  version available at t.
- Test seasons are excluded unless explicitly unlocked (config.ALLOW_TEST_ENV).
"""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config
from .epiweek import epiweek_of

COLUMNS = [
    "unit",
    "reference_date",  # report date (period=day) or epi-week end Saturday (period=epiweek)
    "period",  # "day" or "epiweek"
    "metric",
    "value",
    "source",
    "source_url",
    "vintage_type",  # live | first_reported | final
    "available_at",  # UTC ISO-8601: when this value could first have been known
    "available_at_basis",  # retrieved | published | assumed
    "retrieved_at",  # UTC ISO-8601: when we fetched it
    "raw_sha256",
    "note",
]
KEY = ["unit", "reference_date", "period", "metric"]
VALID_UNITS = set(config.UNITS) | {config.MERGED_DHAKA_CITY}
VALID_PERIODS = {"day", "epiweek"}
VALID_VINTAGES = {"live", "first_reported", "final"}
VALID_BASES = {"retrieved", "published", "assumed"}
MANIFEST_COLUMNS = ["source", "url", "retrieved_at", "sha256", "path", "bytes", "duplicate_of_existing"]


class SeasonLockError(RuntimeError):
    """Raised when code tries to read locked test seasons."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_utc(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        raise ValueError(f"Timestamp {ts!r} has no timezone; pass UTC explicitly.")
    return t.tz_convert("UTC")


# ---------------------------------------------------------------- raw files
def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_raw_snapshot(
    content: bytes,
    source: str,
    url: str,
    extension: str,
    retrieved_at: datetime | None = None,
    raw_dir: Path | None = None,
    manifest_file: Path | None = None,
) -> tuple[str, Path]:
    """Store a raw download unchanged and log it in the manifest.

    Returns (sha256, path). Identical content already stored for the same
    source is not written twice, but the retrieval is still logged.
    """
    raw_dir = raw_dir or config.RAW_DIR
    manifest_file = manifest_file or config.RAW_MANIFEST_FILE
    retrieved_at = retrieved_at or utc_now()
    digest = sha256_bytes(content)
    existing = _existing_raw_path(source, digest, raw_dir)
    if existing is not None:
        path, duplicate = existing, True
    else:
        day_dir = raw_dir / source / retrieved_at.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{retrieved_at.strftime('%H%M%S')}_{digest[:12]}.{extension.lstrip('.')}"
        path.write_bytes(content)
        duplicate = False
    _append_csv(
        manifest_file,
        MANIFEST_COLUMNS,
        [{
            "source": source,
            "url": url,
            "retrieved_at": retrieved_at.isoformat(),
            "sha256": digest,
            "path": str(path.relative_to(config.REPO_ROOT) if path.is_relative_to(config.REPO_ROOT) else path),
            "bytes": len(content),
            "duplicate_of_existing": duplicate,
        }],
    )
    return digest, path


def _existing_raw_path(source: str, digest: str, raw_dir: Path) -> Path | None:
    src_dir = raw_dir / source
    if not src_dir.exists():
        return None
    matches = list(src_dir.rglob(f"*_{digest[:12]}.*"))
    return matches[0] if matches else None


# --------------------------------------------------------------- appending
def _append_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:  # append mode only
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="raise")
        if new_file:
            writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})


def _validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in COLUMNS if c not in df.columns]
    for c in missing:
        if c in ("note", "raw_sha256", "source_url"):
            df[c] = ""
        else:
            raise ValueError(f"Missing required column: {c}")
    bad_units = set(df["unit"]) - VALID_UNITS
    if bad_units:
        raise ValueError(f"Unknown units: {sorted(bad_units)}")
    bad_metrics = set(df["metric"]) - set(config.METRICS)
    if bad_metrics:
        raise ValueError(f"Unknown metrics: {sorted(bad_metrics)}")
    if set(df["period"]) - VALID_PERIODS:
        raise ValueError(f"Unknown periods: {set(df['period']) - VALID_PERIODS}")
    if set(df["vintage_type"]) - VALID_VINTAGES:
        raise ValueError(f"Unknown vintage types: {set(df['vintage_type']) - VALID_VINTAGES}")
    if set(df["available_at_basis"]) - VALID_BASES:
        raise ValueError(f"Unknown availability bases: {set(df['available_at_basis']) - VALID_BASES}")
    for col in ("available_at", "retrieved_at"):
        for v in df[col]:
            to_utc(v)  # raises if naive or unparsable
    pd.to_datetime(df["reference_date"], format="%Y-%m-%d")
    # Values are stored as published; non-integers become empty and are noted.
    clean_vals, notes = [], []
    for v, n in zip(df["value"], df["note"]):
        if v == "" or pd.isna(v):
            clean_vals.append("")
            notes.append(n)
            continue
        try:
            f = float(v)
            ok = f.is_integer() and f >= 0
        except (TypeError, ValueError):
            ok = False
        if ok:
            clean_vals.append(str(int(f)))
            notes.append(n)
        else:
            clean_vals.append("")
            notes.append((str(n) + "; " if n else "") + f"invalid published value {v!r}")
    df = df.copy()
    df["value"] = clean_vals
    df["note"] = notes
    return df


def append_observations(rows: pd.DataFrame, archive_file: Path | None = None) -> int:
    """Append rows to the archive. Exact duplicates (same key, value, source,
    vintage and raw hash) are skipped so reruns are idempotent. Returns the
    number of rows appended."""
    archive_file = archive_file or config.OBSERVATIONS_FILE
    df = _validate_rows(rows.astype(object).fillna(""))
    if archive_file.exists() and archive_file.stat().st_size > 0:
        existing = pd.read_csv(archive_file, dtype=str, keep_default_na=False)
        sig_cols = KEY + ["value", "source", "vintage_type", "raw_sha256"]
        seen = set(map(tuple, existing[sig_cols].values.tolist()))
        mask = [tuple(r) not in seen for r in df[sig_cols].astype(str).values.tolist()]
        df = df[mask]
    if df.empty:
        return 0
    _append_csv(archive_file, COLUMNS, df[COLUMNS].to_dict("records"))
    return len(df)


# ------------------------------------------------------------------ reading
def _load(archive_file: Path) -> pd.DataFrame:
    if not archive_file.exists() or archive_file.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(archive_file, dtype=str, keep_default_na=False)


def _season_of(reference_date: str) -> int:
    d = datetime.strptime(reference_date, "%Y-%m-%d").date()
    return epiweek_of(d)[0]


def get_data(
    as_of,
    metrics: list[str] | None = None,
    units: list[str] | None = None,
    period: str | None = None,
    sources: list[str] | None = None,
    include_test_seasons: bool = False,
    archive_file: Path | None = None,
) -> pd.DataFrame:
    """Return observations as they were known at ``as_of`` (UTC).

    For each (unit, reference_date, period, metric) the row with the latest
    ``available_at`` that is <= as_of is returned. Rows from locked test
    seasons are removed unless ``include_test_seasons`` is True AND the
    environment variable in config.ALLOW_TEST_ENV is "1".
    """
    t = to_utc(as_of)
    if include_test_seasons and not config.test_seasons_unlocked():
        raise SeasonLockError(
            f"Test seasons {sorted(config.TEST_SEASONS)} are locked. Set "
            f"{config.ALLOW_TEST_ENV}=1 only for the final post-lock evaluation."
        )
    df = _load(archive_file or config.OBSERVATIONS_FILE)
    if df.empty:
        out = df.copy()
        out["value"] = pd.Series(dtype="float")
        return out
    avail = pd.to_datetime(df["available_at"], utc=True)
    df = df[avail <= t].copy()
    df["_avail"] = avail[avail <= t]
    if metrics is not None:
        df = df[df["metric"].isin(metrics)]
    if units is not None:
        df = df[df["unit"].isin(units)]
    if period is not None:
        df = df[df["period"] == period]
    if sources is not None:
        df = df[df["source"].isin(sources)]
    if not include_test_seasons and not df.empty:
        seasons = df["reference_date"].map(_season_of)
        df = df[~seasons.isin(config.TEST_SEASONS)]
    if df.empty:
        out = df.drop(columns=["_avail"])
        out["value"] = pd.Series(dtype="float")
        return out
    # Latest version per key as of t; ties broken by file order (later wins).
    df["_order"] = range(len(df))
    df = df.sort_values(["_avail", "_order"]).groupby(KEY, as_index=False).tail(1)
    df = df.drop(columns=["_avail", "_order"]).sort_values(KEY).reset_index(drop=True)
    df["value"] = pd.to_numeric(df["value"].replace("", float("nan")))
    return df


def write_truncated_archive(as_of, src: Path, dst: Path) -> None:
    """Copy only rows available at or before as_of (used by leakage test L10)."""
    t = to_utc(as_of)
    df = _load(src)
    if not df.empty:
        df = df[pd.to_datetime(df["available_at"], utc=True) <= t]
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False, columns=COLUMNS)

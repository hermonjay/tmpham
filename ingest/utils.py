"""Shared helpers used by the ingestion layer.

  * setup_logging       - idempotent logger config.
  * extract_snapshot_date - parse a date out of a filename.
  * detect_business_key - profile-driven natural-key detection.
  * hash_business_key   - stable hash used by MERGE ON clause.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Return a configured logger named 'ingest'. Idempotent."""
    logger = logging.getLogger("ingest")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
        logger.addHandler(handler)
    logger.setLevel(level.upper())
    # Don't propagate to root (avoid double prints when embedded in another app).
    logger.propagate = False
    return logger


# Date parsing: ISO YYYY-MM-DD first, then compact YYYYMMDD.
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
_COMPACT_DATE_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")


def extract_snapshot_date(path: Path) -> datetime:
    """Extract a snapshot date from a filename.

    Supports ISO (``YYYY-MM-DD``) and compact (``YYYYMMDD``) substrings.
    Raises ``ValueError`` when no date is found.
    """
    stem = path.stem
    m = _ISO_DATE_RE.search(stem)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d")
    m = _COMPACT_DATE_RE.search(stem)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d")
    raise ValueError(
        f"Cannot extract snapshot date from filename '{path.name}'. "
        "Expected YYYY-MM-DD or YYYYMMDD substring."
    )


def _matches_any_pattern(column: str, patterns: Iterable[str]) -> bool:
    lower = column.lower()
    return any(re.search(p, lower) for p in patterns)


def profile_columns(df: pd.DataFrame, patterns: Sequence[str]) -> list[dict]:
    """Return per-column profile stats for id-like columns only."""
    n = max(len(df), 1)
    out: list[dict] = []
    for col in df.columns:
        if not _matches_any_pattern(col, patterns):
            continue
        series = df[col]
        nunq = int(series.dropna().nunique())
        out.append(
            {
                "column": col,
                "unique": nunq,
                "cardinality_ratio": nunq / n,
                "null_pct": float(series.isna().mean()),
                "dtype": str(series.dtype),
            }
        )
    return out


def detect_business_key(
    df: pd.DataFrame,
    patterns: Sequence[str],
    min_cardinality_ratio: float = 0.1,
) -> list[str]:
    """Auto-detect the natural/business key columns of ``df``.

    Strategy (deterministic, no randomness):

      1. Filter to id-like column names via regex against ``patterns``.
      2. **Single perfect key**: if one column has cardinality >= 0.95 and
         zero nulls, return it (preferred). Bare ``id`` wins ties.
      3. **Composite key**: union of id-like columns with cardinality >=
         ``min_cardinality_ratio`` and zero nulls, sorted alphabetically.
      4. **Fallback**: all id-like columns, sorted alphabetically.

    Raises ``ValueError`` if no id-like column exists.
    """
    if df.empty:
        raise ValueError("Cannot profile an empty DataFrame.")

    profile = profile_columns(df, patterns)
    if not profile:
        raise ValueError(
            f"No business key candidates found. Columns: {list(df.columns)}. "
            "Adjust id_column_patterns if your key uses a different naming."
        )

    # 1. Perfect single key.
    perfect = [
        p for p in profile
        if p["cardinality_ratio"] >= 0.95 and p["null_pct"] == 0.0
    ]
    if perfect:
        # Prefer literal 'id', then alphabetical.
        perfect.sort(key=lambda p: (0 if p["column"].lower() == "id" else 1, p["column"]))
        return [perfect[0]["column"]]

    # 2. Composite of non-null id-like columns with reasonable cardinality.
    composite = [
        p["column"] for p in profile
        if p["cardinality_ratio"] >= min_cardinality_ratio and p["null_pct"] == 0.0
    ]
    if composite:
        return sorted(composite)

    # 3. Last-resort fallback: all id-like columns.
    return sorted(p["column"] for p in profile)


def hash_business_key_series(series_list: Sequence[pd.Series]) -> pd.Series:
    """Vectorised-ish hash of composite business key columns.

    Returns hex strings (sha256). Nulls replaced with literal ``__NULL__``
    to distinguish ``(None, "x")`` from ``("x", None)``.
    """
    parts: list[pd.Series] = []
    for s in series_list:
        parts.append(s.astype("string").fillna("__NULL__"))
    joined = parts[0]
    sep = "\x1f"  # ASCII unit separator - never in real data.
    for p in parts[1:]:
        joined = joined.str.cat(p, sep=sep)

    def _h(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    return joined.map(_h)

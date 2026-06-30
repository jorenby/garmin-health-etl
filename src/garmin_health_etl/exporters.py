"""Exporters for Garmin Health ETL."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from .store import GARMIN_DATA_COLUMNS, PSV_COLUMNS, PSV_HEADER, SQLiteStore


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _format_psv_value(value: Any) -> str:
    value = _clean(value)
    return "" if value is None else str(value)


def export_psv(store: SQLiteStore, output_path) -> Path:
    """Write the frozen legacy 9-column PSV (backward-compatible format)."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    rows = store.fetch_garmin_data()
    with destination.open("w", encoding="utf-8") as handle:
        handle.write(PSV_HEADER + "\n")
        for row in rows:
            values = [_format_psv_value(row[column]) for column in PSV_COLUMNS]
            handle.write("|".join(values) + "\n")

    return destination


def export_csv(store: SQLiteStore, output_path) -> Path:
    """Write the full garmin_data table as CSV (all expanded columns)."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    rows = store.fetch_garmin_data()
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(GARMIN_DATA_COLUMNS)
        for row in rows:
            writer.writerow([_clean(row[column]) for column in GARMIN_DATA_COLUMNS])

    return destination

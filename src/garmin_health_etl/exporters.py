"""Exporters for Garmin Health ETL."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .store import PSV_HEADER, SQLiteStore


def _format_psv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def export_psv(store: SQLiteStore, output_path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    rows = store.fetch_garmin_data()
    with destination.open("w", encoding="utf-8") as handle:
        handle.write(PSV_HEADER + "\n")
        for row in rows:
            values = [_format_psv_value(row[column]) for column in row.keys()]
            handle.write("|".join(values) + "\n")

    return destination

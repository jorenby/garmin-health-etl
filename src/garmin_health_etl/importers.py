"""Importers for normalized structured Garmin data.

``import-json`` accepts either:

* a *typed* object with any of the top-level arrays ``garmin_data``,
  ``activities``, ``manual_tracking`` (the shape the built-in extractor emits), or
* the legacy shapes that map to ``garmin_data`` only: a single object, an array
  of objects, an object with a top-level ``records`` array, or NDJSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import ActivityRecord, GarminDataRecord, ManualTrackingRecord

_TYPED_KEYS = ("garmin_data", "activities", "manual_tracking")
_RECORD_TYPES = {
    "garmin_data": GarminDataRecord,
    "activities": ActivityRecord,
    "manual_tracking": ManualTrackingRecord,
}


def _load_json_file(input_path: Path) -> Any:
    with input_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_ndjson_file(input_path: Path) -> List[Dict[str, Any]]:
    records = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid NDJSON record at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    f"NDJSON record at line {line_number} must be a JSON object"
                )
            records.append(payload)
    return records


def _coerce_to_dicts(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        if "records" in payload:
            nested = payload["records"]
            if not isinstance(nested, list):
                raise ValueError("'records' must be a JSON array")
            return _coerce_to_dicts(nested)
        return [payload]
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("JSON array items must be objects")
        return payload
    raise ValueError("Input must be a JSON object, JSON array, or NDJSON objects")


def _read_payload(input_path) -> Any:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() == ".ndjson":
        return _load_ndjson_file(path)
    try:
        return _load_json_file(path)
    except json.JSONDecodeError:
        return _load_ndjson_file(path)


def load_payload(input_path) -> Dict[str, list]:
    """Return record lists keyed by table name.

    Always returns all three keys; absent tables map to empty lists.
    """
    raw = _read_payload(input_path)
    result: Dict[str, list] = {key: [] for key in _TYPED_KEYS}

    if isinstance(raw, dict) and any(key in raw for key in _TYPED_KEYS):
        for key in _TYPED_KEYS:
            section = raw.get(key) or []
            if not isinstance(section, list):
                raise ValueError(f"'{key}' must be a JSON array")
            record_cls = _RECORD_TYPES[key]
            result[key] = [record_cls.from_mapping(item) for item in section]
        return result

    # Legacy: everything maps to garmin_data.
    dicts = _coerce_to_dicts(raw)
    result["garmin_data"] = [GarminDataRecord.from_mapping(item) for item in dicts]
    return result


def load_records(input_path) -> List[GarminDataRecord]:
    """Backward-compatible helper returning only the garmin_data records."""
    return load_payload(input_path)["garmin_data"]

"""Importers for normalized structured Garmin data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import GarminDataRecord


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


def _coerce_payload_to_records(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        if "records" in payload:
            nested = payload["records"]
            if not isinstance(nested, list):
                raise ValueError("'records' must be a JSON array")
            return _coerce_payload_to_records(nested)
        return [payload]
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("JSON array items must be objects")
        return payload
    raise ValueError("Input must be a JSON object, JSON array, or NDJSON objects")


def load_records(input_path) -> List[GarminDataRecord]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".ndjson":
        payloads = _load_ndjson_file(path)
    else:
        try:
            payload = _load_json_file(path)
        except json.JSONDecodeError:
            payloads = _load_ndjson_file(path)
        else:
            payloads = _coerce_payload_to_records(payload)

    return [GarminDataRecord.from_mapping(payload) for payload in payloads]

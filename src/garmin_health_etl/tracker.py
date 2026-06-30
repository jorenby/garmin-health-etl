"""Importer for the "Daily Health Tracker" Google Form responses (CSV).

Google Form CSV headers are verbose and change wording over time, so columns
are matched by keyword rather than exact string. The form's rating questions
are all 1-10 higher = better. A former "Stress" question (higher = worse) was
renamed "Calm" (higher = better) on 2026-06-24; this importer maps either
header onto the single ``calm`` column, inverting legacy stress values
(``calm = 11 - stress``) so old and new exports combine cleanly.
"""

from __future__ import annotations

import csv
import datetime as _dt
import re
from pathlib import Path
from typing import Dict, List, Optional

from .models import ManualTrackingRecord

# Canonical field -> predicate over a normalized (lowercased) header.
# Order matters: the first matching rule wins for a given header, and the
# first header that maps to a field claims it.
_HEADER_RULES = [
    ("date", lambda h: "date" in h and "timestamp" not in h),
    ("sleep_quality", lambda h: "sleep" in h),
    ("energy", lambda h: "energy" in h),
    ("mood", lambda h: "mood" in h),
    ("calm", lambda h: "calm" in h),
    ("stress", lambda h: "stress" in h),
    ("appetite", lambda h: "appetite" in h),
    ("supplements", lambda h: "supplement" in h),
    ("exercise_rehab", lambda h: "exercise" in h or "rehab" in h),
    ("symptoms", lambda h: "symptom" in h),
    ("bowel_movement", lambda h: "bowel" in h),
    ("meals_triggers", lambda h: "meal" in h or "trigger" in h),
    ("other_notes", lambda h: "other" in h),
]

_RATING_FIELDS = ("sleep_quality", "energy", "mood", "appetite")
_TEXT_FIELDS = (
    "supplements",
    "exercise_rehab",
    "symptoms",
    "bowel_movement",
    "meals_triggers",
    "other_notes",
)
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m/%d/%y", "%d/%m/%Y")


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", header.strip().lower())


def map_headers(headers) -> Dict[str, str]:
    """Return {canonical_field: original_header} for recognized columns."""
    mapping: Dict[str, str] = {}
    for original in headers:
        norm = _normalize_header(original)
        for field, predicate in _HEADER_RULES:
            if field in mapping:
                continue
            if predicate(norm):
                mapping[field] = original
                break
    return mapping


def parse_rating(value) -> Optional[int]:
    """Extract a 1-10 rating; average ``a-b`` ranges; clamp to [1, 10]."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    rating = sum(numbers) / len(numbers) if len(numbers) >= 2 and "-" in text else numbers[0]
    return max(1, min(10, int(round(rating))))


def parse_date(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Google timestamps look like "6/24/2026 8:05:13"; keep the date part.
    text = text.split(" ")[0]
    for fmt in _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _clean_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def rows_to_records(rows, mapping: Dict[str, str]) -> List[ManualTrackingRecord]:
    records: List[ManualTrackingRecord] = []
    for row in rows:
        date = parse_date(row.get(mapping["date"])) if "date" in mapping else None
        if not date:
            continue  # a row without a usable date cannot be joined

        payload: Dict[str, object] = {"date": date}
        for field in _RATING_FIELDS:
            if field in mapping:
                payload[field] = parse_rating(row.get(mapping[field]))

        # calm: prefer an explicit "calm" column; otherwise invert legacy stress.
        if "calm" in mapping:
            payload["calm"] = parse_rating(row.get(mapping["calm"]))
        elif "stress" in mapping:
            stress = parse_rating(row.get(mapping["stress"]))
            payload["calm"] = None if stress is None else 11 - stress

        for field in _TEXT_FIELDS:
            if field in mapping:
                payload[field] = _clean_text(row.get(mapping[field]))

        records.append(ManualTrackingRecord.from_mapping(payload))
    return records


def load_tracker_csv(input_path) -> List[ManualTrackingRecord]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        mapping = map_headers(headers)
        if "date" not in mapping:
            raise ValueError(
                "Could not find a Date column in the tracker CSV. "
                f"Headers seen: {headers}"
            )
        return rows_to_records(reader, mapping)

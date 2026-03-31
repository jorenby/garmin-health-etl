"""Core data models for Garmin Health ETL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple


def _empty_to_none(value: Any) -> Any:
    if value == "":
        return None
    return value


def _coerce_int(value: Any) -> Optional[int]:
    value = _empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value).strip())


def _coerce_float(value: Any) -> Optional[float]:
    value = _empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).strip())


def _coerce_text(value: Any) -> Optional[str]:
    value = _empty_to_none(value)
    if value is None:
        return None
    return str(value)


@dataclass
class GarminDataRecord:
    date: str
    bed_time: Optional[str] = None
    wake_time: Optional[str] = None
    sleep_score: Optional[int] = None
    hrv_avg: Optional[float] = None
    rhr: Optional[int] = None
    body_battery_recharge: Optional[int] = None
    wake_ups: Optional[int] = None
    restlessness_score: Optional[str] = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GarminDataRecord":
        date = _coerce_text(payload.get("date"))
        if not date:
            raise ValueError("Record is missing required field 'date'")

        return cls(
            date=date,
            bed_time=_coerce_text(payload.get("bed_time")),
            wake_time=_coerce_text(payload.get("wake_time")),
            sleep_score=_coerce_int(payload.get("sleep_score")),
            hrv_avg=_coerce_float(payload.get("hrv_avg")),
            rhr=_coerce_int(payload.get("rhr")),
            body_battery_recharge=_coerce_int(payload.get("body_battery_recharge")),
            wake_ups=_coerce_int(payload.get("wake_ups")),
            restlessness_score=_coerce_text(payload.get("restlessness_score")),
        )


@dataclass
class Summary:
    total_records: int
    date_range: Tuple[Optional[str], Optional[str]]
    missing_sleep_scores: int
    missing_hrv: int
    missing_body_battery: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "date_range": {
                "start": self.date_range[0],
                "end": self.date_range[1],
            },
            "missing_sleep_scores": self.missing_sleep_scores,
            "missing_hrv": self.missing_hrv,
            "missing_body_battery": self.missing_body_battery,
        }

"""Core data models for Garmin Health ETL.

Each record type is described by an ordered ``FieldSpec`` table. That single
source of truth drives:

* the dataclass fields (declared explicitly for typing/readability),
* coercion in ``from_mapping`` (including legacy field aliases), and
* the SQLite schema in :mod:`garmin_health_etl.store`.

A test asserts the dataclasses and the store column lists stay aligned, so the
spec cannot silently drift from the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from typing import Any, Dict, Mapping, Optional, Tuple


# --------------------------------------------------------------------------- #
# Coercion helpers
# --------------------------------------------------------------------------- #
def _empty_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def coerce_int(value: Any) -> Optional[int]:
    value = _empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    return int(round(float(str(value).strip())))


def coerce_float(value: Any) -> Optional[float]:
    value = _empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).strip())


def coerce_text(value: Any) -> Optional[str]:
    value = _empty_to_none(value)
    if value is None:
        return None
    return str(value)


_COERCERS = {
    "int": coerce_int,
    "real": coerce_float,
    "text": coerce_text,
}

# SQLite affinity per coercion kind. Used by the store to build CREATE TABLE.
SQL_TYPES = {
    "int": "INTEGER",
    "real": "REAL",
    "text": "TEXT",
}


class FieldSpec(tuple):
    """(name, kind, *aliases). ``kind`` is one of int/real/text."""

    __slots__ = ()

    def __new__(cls, name: str, kind: str, *aliases: str):
        return super().__new__(cls, (name, kind, aliases))

    @property
    def name(self) -> str:
        return self[0]

    @property
    def kind(self) -> str:
        return self[1]

    @property
    def aliases(self) -> Tuple[str, ...]:
        return self[2]


def _build_from_mapping(spec, cls, payload: Mapping[str, Any]):
    """Instantiate ``cls`` from ``payload`` using ``spec``.

    The first field is treated as the required key (``date`` / ``activity_id``).
    Each field reads its own name first, then any declared legacy aliases.
    """
    kwargs: Dict[str, Any] = {}
    for field in spec:
        coerce = _COERCERS[field.kind]
        raw = payload.get(field.name)
        if raw is None:
            for alias in field.aliases:
                if payload.get(alias) is not None:
                    raw = payload.get(alias)
                    break
        kwargs[field.name] = coerce(raw)

    required = spec[0].name
    if kwargs.get(required) in (None, ""):
        raise ValueError(f"Record is missing required field '{required}'")
    return cls(**kwargs)


# --------------------------------------------------------------------------- #
# garmin_data  (one row per date)
# --------------------------------------------------------------------------- #
GARMIN_DATA_SPEC: Tuple[FieldSpec, ...] = (
    FieldSpec("date", "text"),
    # identity / sleep window
    FieldSpec("bed_time", "text"),
    FieldSpec("wake_time", "text"),
    # sleep
    FieldSpec("sleep_score", "int"),
    FieldSpec("sleep_total_minutes", "int"),
    FieldSpec("deep_minutes", "int"),
    FieldSpec("light_minutes", "int"),
    FieldSpec("rem_minutes", "int"),
    FieldSpec("awake_minutes", "int"),
    FieldSpec("wake_ups", "int"),
    FieldSpec("restlessness_score", "text"),
    FieldSpec("sleep_need", "int"),
    # sleep-window physiology
    FieldSpec("sleep_spo2_avg", "real"),
    FieldSpec("sleep_spo2_lowest", "int"),
    FieldSpec("sleep_resp_avg", "real"),
    FieldSpec("sleep_resp_low", "real"),
    FieldSpec("sleep_resp_high", "real"),
    # HRV  (hrv_avg is the legacy alias for hrv_last_night)
    FieldSpec("hrv_last_night", "real", "hrv_avg"),
    FieldSpec("hrv_status", "text"),
    FieldSpec("hrv_baseline_low", "int"),
    FieldSpec("hrv_baseline_upper", "int"),
    FieldSpec("hrv_weekly_avg", "int"),
    # heart rate  (rhr is the legacy alias for resting_hr)
    FieldSpec("resting_hr", "int", "rhr"),
    FieldSpec("resting_hr_7day_avg", "int"),
    FieldSpec("hr_min", "int"),
    FieldSpec("hr_avg", "int"),
    FieldSpec("hr_max", "int"),
    # stress
    FieldSpec("stress_avg", "int"),
    FieldSpec("stress_max", "int"),
    FieldSpec("stress_rest_seconds", "int"),
    FieldSpec("stress_low_seconds", "int"),
    FieldSpec("stress_medium_seconds", "int"),
    FieldSpec("stress_high_seconds", "int"),
    # body battery  (body_battery_recharge is the legacy alias for bb_charged_overnight)
    FieldSpec("bb_charged_overnight", "int", "body_battery_recharge"),
    FieldSpec("bb_drained", "int"),
    FieldSpec("bb_highest", "int"),
    FieldSpec("bb_lowest", "int"),
    FieldSpec("bb_at_wake", "int"),
    # activity totals
    FieldSpec("steps", "int"),
    FieldSpec("steps_goal", "int"),
    FieldSpec("floors", "real"),
    FieldSpec("distance_m", "real"),
    FieldSpec("moderate_intensity_minutes", "int"),
    FieldSpec("vigorous_intensity_minutes", "int"),
    FieldSpec("active_kcal", "int"),
    FieldSpec("total_kcal", "int"),
    FieldSpec("bmr_kcal", "int"),
    # SpO2 / respiration (whole day)
    FieldSpec("spo2_avg", "real"),
    FieldSpec("spo2_lowest", "int"),
    FieldSpec("resp_avg", "real"),
    FieldSpec("resp_low", "real"),
    FieldSpec("resp_high", "real"),
    # fitness metrics (frequently absent — null-filled)
    FieldSpec("vo2max", "real"),
    FieldSpec("fitness_age", "real"),
    FieldSpec("training_status", "text"),
    FieldSpec("training_readiness", "int"),
    # optional body composition
    FieldSpec("weight", "real"),
    FieldSpec("body_fat_pct", "real"),
)


@dataclass
class GarminDataRecord:
    date: str
    bed_time: Optional[str] = None
    wake_time: Optional[str] = None
    sleep_score: Optional[int] = None
    sleep_total_minutes: Optional[int] = None
    deep_minutes: Optional[int] = None
    light_minutes: Optional[int] = None
    rem_minutes: Optional[int] = None
    awake_minutes: Optional[int] = None
    wake_ups: Optional[int] = None
    restlessness_score: Optional[str] = None
    sleep_need: Optional[int] = None
    sleep_spo2_avg: Optional[float] = None
    sleep_spo2_lowest: Optional[int] = None
    sleep_resp_avg: Optional[float] = None
    sleep_resp_low: Optional[float] = None
    sleep_resp_high: Optional[float] = None
    hrv_last_night: Optional[float] = None
    hrv_status: Optional[str] = None
    hrv_baseline_low: Optional[int] = None
    hrv_baseline_upper: Optional[int] = None
    hrv_weekly_avg: Optional[int] = None
    resting_hr: Optional[int] = None
    resting_hr_7day_avg: Optional[int] = None
    hr_min: Optional[int] = None
    hr_avg: Optional[int] = None
    hr_max: Optional[int] = None
    stress_avg: Optional[int] = None
    stress_max: Optional[int] = None
    stress_rest_seconds: Optional[int] = None
    stress_low_seconds: Optional[int] = None
    stress_medium_seconds: Optional[int] = None
    stress_high_seconds: Optional[int] = None
    bb_charged_overnight: Optional[int] = None
    bb_drained: Optional[int] = None
    bb_highest: Optional[int] = None
    bb_lowest: Optional[int] = None
    bb_at_wake: Optional[int] = None
    steps: Optional[int] = None
    steps_goal: Optional[int] = None
    floors: Optional[float] = None
    distance_m: Optional[float] = None
    moderate_intensity_minutes: Optional[int] = None
    vigorous_intensity_minutes: Optional[int] = None
    active_kcal: Optional[int] = None
    total_kcal: Optional[int] = None
    bmr_kcal: Optional[int] = None
    spo2_avg: Optional[float] = None
    spo2_lowest: Optional[int] = None
    resp_avg: Optional[float] = None
    resp_low: Optional[float] = None
    resp_high: Optional[float] = None
    vo2max: Optional[float] = None
    fitness_age: Optional[float] = None
    training_status: Optional[str] = None
    training_readiness: Optional[int] = None
    weight: Optional[float] = None
    body_fat_pct: Optional[float] = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GarminDataRecord":
        return _build_from_mapping(GARMIN_DATA_SPEC, cls, payload)


# --------------------------------------------------------------------------- #
# activities  (one row per logged workout)
# --------------------------------------------------------------------------- #
ACTIVITY_SPEC: Tuple[FieldSpec, ...] = (
    FieldSpec("activity_id", "text"),
    FieldSpec("date", "text"),
    FieldSpec("start_time", "text"),
    FieldSpec("type", "text", "activity_type"),
    FieldSpec("name", "text"),
    FieldSpec("duration_seconds", "real", "duration"),
    FieldSpec("distance_m", "real", "distance"),
    FieldSpec("avg_hr", "int", "averageHR"),
    FieldSpec("max_hr", "int", "maxHR"),
    FieldSpec("aerobic_training_effect", "real"),
    FieldSpec("anaerobic_training_effect", "real"),
    FieldSpec("training_load", "real", "activityTrainingLoad"),
    FieldSpec("calories", "int"),
    FieldSpec("avg_speed_mps", "real", "averageSpeed"),
)


@dataclass
class ActivityRecord:
    activity_id: str
    date: Optional[str] = None
    start_time: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    duration_seconds: Optional[float] = None
    distance_m: Optional[float] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    aerobic_training_effect: Optional[float] = None
    anaerobic_training_effect: Optional[float] = None
    training_load: Optional[float] = None
    calories: Optional[int] = None
    avg_speed_mps: Optional[float] = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ActivityRecord":
        return _build_from_mapping(ACTIVITY_SPEC, cls, payload)


# --------------------------------------------------------------------------- #
# manual_tracking  (one row per date, from the "Daily Health Tracker" Form)
# --------------------------------------------------------------------------- #
# All 1-10 ratings are stored higher = better. "calm" replaces a former
# "stress" field (higher = better == calmer); the tracker importer inverts
# legacy stress values to this convention.
MANUAL_TRACKING_SPEC: Tuple[FieldSpec, ...] = (
    FieldSpec("date", "text"),
    FieldSpec("sleep_quality", "int"),
    FieldSpec("energy", "int"),
    FieldSpec("mood", "int"),
    FieldSpec("calm", "int"),
    FieldSpec("appetite", "int"),
    FieldSpec("supplements", "text"),
    FieldSpec("exercise_rehab", "text"),
    FieldSpec("symptoms", "text"),
    FieldSpec("bowel_movement", "text"),
    FieldSpec("meals_triggers", "text"),
    FieldSpec("other_notes", "text"),
)


@dataclass
class ManualTrackingRecord:
    date: str
    sleep_quality: Optional[int] = None
    energy: Optional[int] = None
    mood: Optional[int] = None
    calm: Optional[int] = None
    appetite: Optional[int] = None
    supplements: Optional[str] = None
    exercise_rehab: Optional[str] = None
    symptoms: Optional[str] = None
    bowel_movement: Optional[str] = None
    meals_triggers: Optional[str] = None
    other_notes: Optional[str] = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ManualTrackingRecord":
        return _build_from_mapping(MANUAL_TRACKING_SPEC, cls, payload)


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #
@dataclass
class Summary:
    total_records: int
    date_range: Tuple[Optional[str], Optional[str]]
    missing_sleep_scores: int
    missing_hrv: int
    missing_body_battery: int
    activities_count: int = 0
    manual_tracking_count: int = 0

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
            "activities_count": self.activities_count,
            "manual_tracking_count": self.manual_tracking_count,
        }


def spec_field_names(spec: Tuple[FieldSpec, ...]) -> Tuple[str, ...]:
    return tuple(field.name for field in spec)


def dataclass_field_names(cls) -> Tuple[str, ...]:
    return tuple(f.name for f in dataclass_fields(cls))

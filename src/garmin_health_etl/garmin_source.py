"""Built-in Garmin Connect extractor.

Design: the *network* layer (login + per-endpoint fetch) is isolated from the
*normalization* layer (pure functions mapping raw API dicts to the repo's
normalized field names). Normalization has no third-party imports and is fully
unit-tested with synthetic API payloads, so the brittle part (field mapping)
is verified without credentials or network access.

Resilience rule: every endpoint is fetched independently and any failure or
absent metric becomes ``None`` rather than crashing the run. Garmin's API is
inconsistent about what a given watch reports.

Credentials are read from the environment at runtime and never persisted by
this module:

* ``GARMIN_EMAIL`` / ``GARMIN_PASSWORD`` — account login, or
* ``GARMINTOKENS`` — path to a garth token cache directory (token-only login).
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Pure helpers (no network, no third-party deps)
# --------------------------------------------------------------------------- #
def _dig(obj: Any, *keys: Any, default: Any = None) -> Any:
    """Safely walk nested dicts/lists; return ``default`` on any miss."""
    cur = obj
    for key in keys:
        if cur is None:
            return default
        try:
            if isinstance(key, int):
                cur = cur[key]
            else:
                cur = cur.get(key)
        except (KeyError, IndexError, TypeError, AttributeError):
            return default
    return cur if cur is not None else default


def _seconds_to_minutes(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value) / 60.0))
    except (TypeError, ValueError):
        return None


def _ms_to_hhmm(value: Any) -> Optional[str]:
    """Convert a Garmin *local* epoch-millis timestamp to ``HH:MM``."""
    if value is None:
        return None
    try:
        # Local timestamps are wall-clock encoded as if UTC, so read them in UTC.
        return _dt.datetime.fromtimestamp(
            float(value) / 1000.0, tz=_dt.timezone.utc
        ).strftime("%H:%M")
    except (TypeError, ValueError, OSError):
        return None


def _iter_dates(start: str, end: str):
    d0 = _dt.date.fromisoformat(start)
    d1 = _dt.date.fromisoformat(end)
    if d1 < d0:
        raise ValueError("end date is before start date")
    cur = d0
    while cur <= d1:
        yield cur.isoformat()
        cur += _dt.timedelta(days=1)


# --------------------------------------------------------------------------- #
# Normalization (pure, unit-tested)
# --------------------------------------------------------------------------- #
def _training_status_text(status: Any) -> Optional[str]:
    """Best-effort pull of a training-status label from a varied payload."""
    if not isinstance(status, dict):
        return None
    # The endpoint nests the label differently across firmware versions; try
    # the common locations and fall back to None.
    candidate = _dig(
        status,
        "mostRecentTrainingStatus",
        "latestTrainingStatusData",
    )
    if isinstance(candidate, dict):
        for value in candidate.values():
            label = _dig(value, "trainingStatusFeedbackPhrase") or _dig(
                value, "trainingStatus"
            )
            if label:
                return str(label)
    return status.get("trainingStatus") if isinstance(status.get("trainingStatus"), str) else None


def normalize_day(date: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map the per-endpoint raw dicts for one day to a garmin_data record dict.

    ``raw`` keys: summary, sleep, hrv, spo2, respiration, rhr, max_metrics,
    training_readiness, training_status, fitness_age. Any may be ``None``.
    """
    summary = raw.get("summary") or {}
    sleep = raw.get("sleep") or {}
    sleep_dto = sleep.get("dailySleepDTO") or {}
    hrv = _dig(raw, "hrv", "hrvSummary", default={}) or {}
    spo2 = raw.get("spo2") or {}
    resp = raw.get("respiration") or {}
    max_metrics = raw.get("max_metrics")
    readiness = raw.get("training_readiness")
    status = raw.get("training_status") or {}

    record: Dict[str, Any] = {
        "date": date,
        # sleep window
        "bed_time": _ms_to_hhmm(sleep_dto.get("sleepStartTimestampLocal")),
        "wake_time": _ms_to_hhmm(sleep_dto.get("sleepEndTimestampLocal")),
        # sleep
        "sleep_score": _dig(sleep_dto, "sleepScores", "overall", "value"),
        "sleep_total_minutes": _seconds_to_minutes(sleep_dto.get("sleepTimeSeconds")),
        "deep_minutes": _seconds_to_minutes(sleep_dto.get("deepSleepSeconds")),
        "light_minutes": _seconds_to_minutes(sleep_dto.get("lightSleepSeconds")),
        "rem_minutes": _seconds_to_minutes(sleep_dto.get("remSleepSeconds")),
        "awake_minutes": _seconds_to_minutes(sleep_dto.get("awakeSleepSeconds")),
        "wake_ups": sleep.get("awakeCount", sleep_dto.get("awakeCount")),
        "restlessness_score": _dig(sleep_dto, "sleepScores", "overall", "qualifierKey"),
        "sleep_need": _seconds_to_minutes(_dig(sleep_dto, "sleepNeed", "actual")),
        # sleep-window physiology
        "sleep_spo2_avg": sleep.get("averageSpO2Value", sleep.get("averageSpO2")),
        "sleep_spo2_lowest": sleep.get("lowestSpO2Value", sleep.get("lowestSpO2")),
        "sleep_resp_avg": sleep.get("averageRespirationValue"),
        "sleep_resp_low": sleep.get("lowestRespirationValue"),
        "sleep_resp_high": sleep.get("highestRespirationValue"),
        # HRV
        "hrv_last_night": hrv.get("lastNightAvg"),
        "hrv_status": hrv.get("status"),
        "hrv_baseline_low": _dig(hrv, "baseline", "balancedLow"),
        "hrv_baseline_upper": _dig(hrv, "baseline", "balancedUpper"),
        "hrv_weekly_avg": hrv.get("weeklyAvg"),
        # heart rate
        "resting_hr": summary.get("restingHeartRate"),
        "resting_hr_7day_avg": summary.get("lastSevenDaysAvgRestingHeartRate"),
        "hr_min": summary.get("minHeartRate"),
        "hr_avg": summary.get("averageHeartRate"),
        "hr_max": summary.get("maxHeartRate"),
        # stress
        "stress_avg": summary.get("averageStressLevel"),
        "stress_max": summary.get("maxStressLevel"),
        "stress_rest_seconds": summary.get("restStressDuration"),
        "stress_low_seconds": summary.get("lowStressDuration"),
        "stress_medium_seconds": summary.get("mediumStressDuration"),
        "stress_high_seconds": summary.get("highStressDuration"),
        # body battery
        "bb_charged_overnight": summary.get("bodyBatteryChargedValue"),
        "bb_drained": summary.get("bodyBatteryDrainedValue"),
        "bb_highest": summary.get("bodyBatteryHighestValue"),
        "bb_lowest": summary.get("bodyBatteryLowestValue"),
        "bb_at_wake": sleep.get("bodyBatteryChange", summary.get("bodyBatteryAtWakeTime")),
        # activity totals
        "steps": summary.get("totalSteps"),
        "steps_goal": summary.get("dailyStepGoal"),
        "floors": summary.get("floorsAscended"),
        "distance_m": summary.get("totalDistanceMeters"),
        "moderate_intensity_minutes": summary.get("moderateIntensityMinutes"),
        "vigorous_intensity_minutes": summary.get("vigorousIntensityMinutes"),
        "active_kcal": summary.get("activeKilocalories"),
        "total_kcal": summary.get("totalKilocalories"),
        "bmr_kcal": summary.get("bmrKilocalories"),
        # whole-day SpO2 / respiration
        "spo2_avg": spo2.get("averageSpO2", summary.get("averageSpo2")),
        "spo2_lowest": spo2.get("lowestSpO2", summary.get("lowestSpo2")),
        "resp_avg": resp.get("avgWakingRespirationValue", summary.get("avgWakingRespirationValue")),
        "resp_low": resp.get("lowestRespirationValue", summary.get("lowestRespirationValue")),
        "resp_high": resp.get("highestRespirationValue", summary.get("highestRespirationValue")),
        # fitness metrics (often absent)
        "vo2max": _dig(max_metrics, 0, "generic", "vo2MaxValue") if max_metrics else None,
        "fitness_age": raw.get("fitness_age"),
        "training_status": _training_status_text(status),
        "training_readiness": _dig(readiness, 0, "score") if readiness else None,
        # body composition (only if enabled / returned)
        "weight": None,
        "body_fat_pct": None,
    }
    return record


def normalize_activity(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map one raw Garmin activity dict to an ActivityRecord dict."""
    start_local = raw.get("startTimeLocal") or raw.get("startTimeGMT")
    date = start_local[:10] if isinstance(start_local, str) and len(start_local) >= 10 else None
    return {
        "activity_id": raw.get("activityId"),
        "date": date,
        "start_time": start_local,
        "type": _dig(raw, "activityType", "typeKey"),
        "name": raw.get("activityName"),
        "duration_seconds": raw.get("duration"),
        "distance_m": raw.get("distance"),
        "avg_hr": raw.get("averageHR"),
        "max_hr": raw.get("maxHR"),
        "aerobic_training_effect": raw.get("aerobicTrainingEffect"),
        "anaerobic_training_effect": raw.get("anaerobicTrainingEffect"),
        "training_load": raw.get("activityTrainingLoad"),
        "calories": raw.get("calories"),
        "avg_speed_mps": raw.get("averageSpeed"),
    }


# --------------------------------------------------------------------------- #
# Network layer
# --------------------------------------------------------------------------- #
def _safe(label: str, fn: Callable[[], Any]) -> Any:
    """Run a fetch, returning ``None`` (and logging) on any failure."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - resilience rule: never crash a run
        log.warning("Garmin fetch failed for %s: %s", label, exc)
        return None


def login_from_env():
    """Authenticate a garminconnect client using environment credentials."""
    try:
        from garminconnect import Garmin
    except ImportError as exc:  # pragma: no cover - exercised via the [garmin] extra
        raise SystemExit(
            "python-garminconnect is required for `extract`. "
            "Install it with:  uv sync --extra garmin"
        ) from exc

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    tokenstore = os.environ.get("GARMINTOKENS")

    if email and password:
        client = Garmin(email, password)
        client.login(tokenstore)
    elif tokenstore:
        client = Garmin()
        client.login(tokenstore)
    else:
        raise SystemExit(
            "Set GARMIN_EMAIL and GARMIN_PASSWORD (or GARMINTOKENS) in the "
            "environment before running `extract`."
        )
    return client


def fetch_day(client, date: str) -> Dict[str, Any]:
    """Fetch every per-day endpoint for one date, each guarded independently."""
    return {
        "summary": _safe("summary", lambda: client.get_user_summary(date)),
        "sleep": _safe("sleep", lambda: client.get_sleep_data(date)),
        "hrv": _safe("hrv", lambda: client.get_hrv_data(date)),
        "spo2": _safe("spo2", lambda: client.get_spo2_data(date)),
        "respiration": _safe("respiration", lambda: client.get_respiration_data(date)),
        "rhr": _safe("rhr", lambda: client.get_rhr_day(date)),
        "max_metrics": _safe("max_metrics", lambda: client.get_max_metrics(date)),
        "training_readiness": _safe(
            "training_readiness", lambda: client.get_training_readiness(date)
        ),
        "training_status": _safe(
            "training_status", lambda: client.get_training_status(date)
        ),
        "fitness_age": _safe(
            "fitness_age",
            lambda: _dig(client.get_fitnessage_data(date), "achievableFitnessAge"),
        ),
    }


def extract_to_payload(
    start: str,
    end: str,
    include_activities: bool = True,
    client=None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Pull a date range from Garmin Connect into an importable payload dict."""
    if client is None:
        client = login_from_env()

    garmin_data: List[Dict[str, Any]] = []
    for date in _iter_dates(start, end):
        raw = fetch_day(client, date)
        garmin_data.append(normalize_day(date, raw))

    activities: List[Dict[str, Any]] = []
    if include_activities:
        raw_activities = _safe(
            "activities", lambda: client.get_activities_by_date(start, end)
        ) or []
        for raw in raw_activities:
            normalized = normalize_activity(raw)
            if normalized.get("activity_id") is not None:
                activities.append(normalized)

    return {"garmin_data": garmin_data, "activities": activities}

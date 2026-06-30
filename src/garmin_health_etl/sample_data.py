"""Deterministic synthetic dataset generator.

Produces fully synthetic (non-real) data so the README, sample report and tests
have something to render against without shipping any real health data. The
generator is stdlib-only (no numpy) so it works on a base install.

The data has deliberate structure that mirrors the project's real findings:

* subjective **calm -> energy** is positive (the dominant lever),
* Garmin **recovery metrics (HRV, sleep score, Body Battery) -> energy** are
  near zero (the watch measures recovery, not fatigue),
* prior-day movement -> next-day recovery is near zero,
* overnight SpO2 dips below 85% on many nights,
* activity drifts down over the window.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

_START = _dt.date(2025, 1, 6)
_SUPPLEMENTS = [
    "Magnesium glycinate, vitamin D3, krill oil",
    "Magnesium glycinate, vitamin D3, krill oil, MSM",
    "Forgot morning supplements",
    "Magnesium glycinate, vitamin D3",
]
_EXERCISE = ["Walk", "Walk + mobility", "Rest day", "Run", "Ultimate", "Yoga + walk"]
_SYMPTOMS = ["None", "None", "Tension headache", "Sinus congestion", "Joint stiffness"]
_BOWEL = ["1 normal", "2 normal", "None", "1 loose"]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _rating(value: float) -> int:
    return int(round(_clamp(value, 1, 10)))


def _build_day(rng: random.Random, idx: int, n_days: int) -> Tuple[Dict, List[Dict], Dict]:
    date = (_START + _dt.timedelta(days=idx)).isoformat()
    decline = idx / max(1, n_days - 1)  # 0 -> 1 across the window

    # Latent drivers (independent): stress vs recovery.
    stress = rng.gauss(0, 1)
    recovery = rng.gauss(0, 1)

    calm = _rating(6.4 - 1.7 * stress + rng.gauss(0, 0.8))
    energy = _rating(2.6 + 0.62 * calm + rng.gauss(0, 1.0))  # calm -> energy (+)
    mood = _rating(3.0 + 0.5 * calm + 0.2 * energy + rng.gauss(0, 1.0))
    sleep_quality = _rating(4.0 + 0.4 * recovery * 2 + rng.gauss(0, 1.2))
    appetite = _rating(6 + rng.gauss(0, 1.5))

    hrv = round(_clamp(46 + 8 * recovery + rng.gauss(0, 3), 22, 70), 0)
    bb = int(_clamp(56 + 11 * recovery + rng.gauss(0, 6), 5, 100))  # recovery, not energy
    sleep_score = int(_clamp(76 + 8 * recovery + rng.gauss(0, 6), 20, 100))
    garmin_stress = int(_clamp(30 + 12 * stress + rng.gauss(0, 5), 5, 95))

    steps = int(max(0, rng.gauss(7400 - 1800 * decline, 2200)))  # drifts down
    moderate = int(max(0, rng.gauss(22 - 10 * decline, 10)))
    vigorous = int(max(0, rng.gauss(7 - 4 * decline, 5)))
    spo2_low = int(_clamp(round(86 + rng.gauss(0, 3)), 74, 99))  # many nights <=85

    sleep_minutes = int(_clamp(rng.gauss(465, 45), 240, 600))
    deep = int(sleep_minutes * 0.18)
    rem = int(sleep_minutes * 0.22)
    awake = int(max(0, rng.gauss(25, 12)))
    light = max(0, sleep_minutes - deep - rem - awake)

    garmin = {
        "date": date,
        "bed_time": "23:%02d" % rng.randint(0, 59),
        "wake_time": "0%d:%02d" % (rng.randint(6, 7), rng.randint(0, 59)),
        "sleep_score": sleep_score,
        "sleep_total_minutes": sleep_minutes,
        "deep_minutes": deep,
        "light_minutes": light,
        "rem_minutes": rem,
        "awake_minutes": awake,
        "wake_ups": rng.randint(0, 4),
        "restlessness_score": rng.choice(["EXCELLENT", "GOOD", "FAIR", "POOR"]),
        "sleep_need": 480,
        "sleep_spo2_avg": round(_clamp(94 + rng.gauss(0, 1.5), 88, 99), 0),
        "sleep_spo2_lowest": spo2_low,
        "sleep_resp_avg": round(_clamp(14 + rng.gauss(0, 1), 10, 20), 1),
        "sleep_resp_low": round(_clamp(11 + rng.gauss(0, 1), 8, 16), 1),
        "sleep_resp_high": round(_clamp(19 + rng.gauss(0, 1.5), 14, 26), 1),
        "hrv_last_night": hrv,
        "hrv_status": rng.choice(["BALANCED", "BALANCED", "LOW", "UNBALANCED"]),
        "hrv_baseline_low": 41,
        "hrv_baseline_upper": 58,
        "hrv_weekly_avg": int(hrv + rng.gauss(0, 2)),
        "resting_hr": int(_clamp(54 + rng.gauss(0, 3), 44, 70)),
        "resting_hr_7day_avg": int(_clamp(54 + rng.gauss(0, 2), 44, 70)),
        "hr_min": int(_clamp(46 + rng.gauss(0, 3), 38, 60)),
        "hr_avg": int(_clamp(64 + rng.gauss(0, 4), 50, 85)),
        "hr_max": int(_clamp(118 + rng.gauss(0, 12), 90, 175)),
        "stress_avg": garmin_stress,
        "stress_max": int(_clamp(garmin_stress + rng.gauss(40, 10), 50, 100)),
        "stress_rest_seconds": rng.randint(20000, 40000),
        "stress_low_seconds": rng.randint(10000, 25000),
        "stress_medium_seconds": rng.randint(3000, 12000),
        "stress_high_seconds": rng.randint(500, 8000),
        "bb_charged_overnight": bb,
        "bb_drained": int(_clamp(bb + rng.gauss(5, 8), 5, 100)),
        "bb_highest": int(_clamp(bb + rng.gauss(20, 8), 20, 100)),
        "bb_lowest": int(_clamp(rng.gauss(12, 6), 1, 40)),
        "bb_at_wake": int(_clamp(bb + rng.gauss(-3, 5), 5, 100)),
        "steps": steps,
        "steps_goal": 8000,
        "floors": float(rng.randint(2, 18)),
        "distance_m": round(steps * 0.72, 1),
        "moderate_intensity_minutes": moderate,
        "vigorous_intensity_minutes": vigorous,
        "active_kcal": int(max(120, rng.gauss(450, 160))),
        "total_kcal": int(max(1400, rng.gauss(2300, 250))),
        "bmr_kcal": int(rng.gauss(1750, 60)),
        "spo2_avg": round(_clamp(95 + rng.gauss(0, 1), 90, 99), 0),
        "spo2_lowest": spo2_low,
        "resp_avg": round(_clamp(14 + rng.gauss(0, 1), 10, 20), 1),
        "resp_low": round(_clamp(10 + rng.gauss(0, 1), 7, 14), 1),
        "resp_high": round(_clamp(20 + rng.gauss(0, 2), 15, 28), 1),
        # fitness metrics deliberately left null on most days (resilience demo)
        "vo2max": 47.0 if idx % 30 == 0 else None,
        "fitness_age": 38.0 if idx % 30 == 0 else None,
        "training_status": "MAINTAINING" if idx % 15 == 0 else None,
        "training_readiness": None,
        "weight": None,
        "body_fat_pct": None,
    }

    # Activities: a workout on roughly 1 in 3 days, fewer later in the window.
    activities: List[Dict] = []
    if rng.random() < 0.35 * (1 - 0.4 * decline):
        atype = rng.choice(["running", "walking", "ultimate_disc", "yoga"])
        dur = rng.randint(1500, 5400)
        activities.append({
            "activity_id": f"{date}-1",
            "date": date,
            "start_time": f"{date} 17:30:00",
            "type": atype,
            "name": atype.replace("_", " ").title(),
            "duration_seconds": dur,
            "distance_m": round(dur * rng.uniform(1.5, 3.0), 1) if atype != "yoga" else 0.0,
            "avg_hr": rng.randint(110, 150),
            "max_hr": rng.randint(150, 180),
            "aerobic_training_effect": round(rng.uniform(1.5, 4.0), 1),
            "anaerobic_training_effect": round(rng.uniform(0.0, 2.0), 1),
            "training_load": round(rng.uniform(40, 220), 1),
            "calories": rng.randint(150, 700),
            "avg_speed_mps": round(rng.uniform(1.5, 3.4), 2),
        })

    # Manual tracker row (skip ~18% of days to mimic real logging gaps).
    tracker = {}
    if rng.random() > 0.18:
        tracker = {
            "Timestamp": f"{date} 21:30:00",
            "Date": date,
            "Perceived sleep quality (1-10)": sleep_quality,
            "Perceived energy (1-10)": energy,
            "Mood (1-10)": mood,
            "Calm (1-10)": calm,
            "Appetite (1-10)": appetite,
            "Supplements taken": rng.choice(_SUPPLEMENTS),
            "Exercise/rehab done": rng.choice(_EXERCISE),
            "Symptoms": rng.choice(_SYMPTOMS),
            "Bowel movement": rng.choice(_BOWEL),
            "Meals / possible triggers": "",
            "Other notes": "",
        }

    return garmin, activities, tracker


def generate(days: int = 120, seed: int = 42):
    """Return (garmin_payload_dict, tracker_rows_list)."""
    rng = random.Random(seed)
    garmin_data: List[Dict] = []
    activities: List[Dict] = []
    tracker_rows: List[Dict] = []
    for idx in range(days):
        g, acts, t = _build_day(rng, idx, days)
        garmin_data.append(g)
        activities.extend(acts)
        if t:
            tracker_rows.append(t)
    return {"garmin_data": garmin_data, "activities": activities}, tracker_rows


_TRACKER_HEADERS = [
    "Timestamp",
    "Date",
    "Perceived sleep quality (1-10)",
    "Perceived energy (1-10)",
    "Mood (1-10)",
    "Calm (1-10)",
    "Appetite (1-10)",
    "Supplements taken",
    "Exercise/rehab done",
    "Symptoms",
    "Bowel movement",
    "Meals / possible triggers",
    "Other notes",
]


def write_sample(output_dir, days: int = 120, seed: int = 42) -> List[Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload, tracker_rows = generate(days=days, seed=seed)

    json_path = out / "sample_garmin.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    csv_path = out / "sample_tracker.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_TRACKER_HEADERS)
        writer.writeheader()
        writer.writerows(tracker_rows)

    return [json_path, csv_path]

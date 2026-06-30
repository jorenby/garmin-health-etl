import unittest

import _path  # noqa: F401

from garmin_health_etl.garmin_source import (  # noqa: E402
    _dig,
    _iter_dates,
    _ms_to_hhmm,
    _seconds_to_minutes,
    normalize_activity,
    normalize_day,
)


class HelperTests(unittest.TestCase):
    def test_dig_handles_missing(self):
        self.assertEqual(5, _dig({"a": {"b": 5}}, "a", "b"))
        self.assertIsNone(_dig({"a": {}}, "a", "b"))
        self.assertIsNone(_dig(None, "a"))
        self.assertEqual(7, _dig([{"x": 7}], 0, "x"))

    def test_seconds_to_minutes(self):
        self.assertEqual(60, _seconds_to_minutes(3600))
        self.assertIsNone(_seconds_to_minutes(None))

    def test_ms_to_hhmm(self):
        # 2026-01-01 22:30 local encoded as ms.
        ms = 1767306600000  # arbitrary; just assert HH:MM shape
        self.assertRegex(_ms_to_hhmm(ms), r"^\d{2}:\d{2}$")
        self.assertIsNone(_ms_to_hhmm(None))

    def test_iter_dates(self):
        self.assertEqual(
            ["2026-01-01", "2026-01-02", "2026-01-03"],
            list(_iter_dates("2026-01-01", "2026-01-03")),
        )
        with self.assertRaises(ValueError):
            list(_iter_dates("2026-01-03", "2026-01-01"))


class NormalizeDayTests(unittest.TestCase):
    def test_maps_known_summary_and_sleep_fields(self):
        raw = {
            "summary": {
                "totalSteps": 8200,
                "restingHeartRate": 53,
                "lastSevenDaysAvgRestingHeartRate": 54,
                "averageStressLevel": 31,
                "maxStressLevel": 88,
                "highStressDuration": 4200,
                "bodyBatteryChargedValue": 62,
                "moderateIntensityMinutes": 20,
                "vigorousIntensityMinutes": 8,
                "activeKilocalories": 480,
            },
            "sleep": {
                "dailySleepDTO": {
                    "sleepTimeSeconds": 27000,
                    "deepSleepSeconds": 5400,
                    "sleepScores": {"overall": {"value": 84, "qualifierKey": "GOOD"}},
                },
                "awakeCount": 2,
            },
            "hrv": {"hrvSummary": {"lastNightAvg": 46, "status": "BALANCED",
                                    "baseline": {"balancedLow": 41, "balancedUpper": 58},
                                    "weeklyAvg": 45}},
            "spo2": {"averageSpO2": 95, "lowestSpO2": 86},
            "respiration": {"avgWakingRespirationValue": 14},
            "max_metrics": [{"generic": {"vo2MaxValue": 47.0}}],
            "training_readiness": [{"score": 70}],
        }
        rec = normalize_day("2026-01-01", raw)
        self.assertEqual("2026-01-01", rec["date"])
        self.assertEqual(8200, rec["steps"])
        self.assertEqual(53, rec["resting_hr"])
        self.assertEqual(54, rec["resting_hr_7day_avg"])
        self.assertEqual(84, rec["sleep_score"])
        self.assertEqual("GOOD", rec["restlessness_score"])
        self.assertEqual(450, rec["sleep_total_minutes"])
        self.assertEqual(2, rec["wake_ups"])
        self.assertEqual(46, rec["hrv_last_night"])
        self.assertEqual("BALANCED", rec["hrv_status"])
        self.assertEqual(86, rec["spo2_lowest"])
        self.assertEqual(47.0, rec["vo2max"])
        self.assertEqual(70, rec["training_readiness"])

    def test_resilient_to_empty_payload(self):
        rec = normalize_day("2026-01-01", {})
        self.assertEqual("2026-01-01", rec["date"])
        self.assertIsNone(rec["steps"])
        self.assertIsNone(rec["hrv_last_night"])


class NormalizeActivityTests(unittest.TestCase):
    def test_maps_activity(self):
        raw = {
            "activityId": 12345,
            "startTimeLocal": "2026-01-01 17:30:00",
            "activityType": {"typeKey": "running"},
            "activityName": "Afternoon Run",
            "duration": 1800.0,
            "distance": 5000.0,
            "averageHR": 140,
            "activityTrainingLoad": 120.0,
        }
        rec = normalize_activity(raw)
        self.assertEqual(12345, rec["activity_id"])
        self.assertEqual("2026-01-01", rec["date"])
        self.assertEqual("running", rec["type"])
        self.assertEqual(140, rec["avg_hr"])
        self.assertEqual(120.0, rec["training_load"])


if __name__ == "__main__":
    unittest.main()

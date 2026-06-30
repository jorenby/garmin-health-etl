import unittest

import _path  # noqa: F401  (sets up sys.path)

from garmin_health_etl.models import (  # noqa: E402
    ACTIVITY_SPEC,
    GARMIN_DATA_SPEC,
    MANUAL_TRACKING_SPEC,
    ActivityRecord,
    GarminDataRecord,
    ManualTrackingRecord,
    dataclass_field_names,
    spec_field_names,
)


class SpecAlignmentTests(unittest.TestCase):
    def test_specs_match_dataclasses(self):
        self.assertEqual(
            spec_field_names(GARMIN_DATA_SPEC), dataclass_field_names(GarminDataRecord)
        )
        self.assertEqual(
            spec_field_names(ACTIVITY_SPEC), dataclass_field_names(ActivityRecord)
        )
        self.assertEqual(
            spec_field_names(MANUAL_TRACKING_SPEC),
            dataclass_field_names(ManualTrackingRecord),
        )

    def test_specs_match_store_columns(self):
        from garmin_health_etl.store import (
            ACTIVITY_COLUMNS,
            GARMIN_DATA_COLUMNS,
            MANUAL_TRACKING_COLUMNS,
        )

        self.assertEqual(GARMIN_DATA_COLUMNS, spec_field_names(GARMIN_DATA_SPEC))
        self.assertEqual(ACTIVITY_COLUMNS, spec_field_names(ACTIVITY_SPEC))
        self.assertEqual(MANUAL_TRACKING_COLUMNS, spec_field_names(MANUAL_TRACKING_SPEC))


class GarminRecordTests(unittest.TestCase):
    def test_legacy_aliases_map_to_new_fields(self):
        record = GarminDataRecord.from_mapping(
            {
                "date": "2026-01-01",
                "hrv_avg": 41.5,
                "rhr": 54,
                "body_battery_recharge": 68,
            }
        )
        self.assertEqual(41.5, record.hrv_last_night)
        self.assertEqual(54, record.resting_hr)
        self.assertEqual(68, record.bb_charged_overnight)

    def test_new_field_names_take_precedence(self):
        record = GarminDataRecord.from_mapping(
            {"date": "2026-01-01", "hrv_last_night": 50.0, "hrv_avg": 41.5}
        )
        self.assertEqual(50.0, record.hrv_last_night)

    def test_empty_strings_become_none_and_required_date(self):
        record = GarminDataRecord.from_mapping({"date": "2026-01-01", "steps": ""})
        self.assertIsNone(record.steps)
        with self.assertRaises(ValueError):
            GarminDataRecord.from_mapping({"steps": 100})

    def test_full_field_round_trip(self):
        record = GarminDataRecord.from_mapping(
            {"date": "2026-01-02", "deep_minutes": 70, "spo2_lowest": 88}
        )
        self.assertEqual(70, record.deep_minutes)
        self.assertEqual(88, record.spo2_lowest)


class ActivityRecordTests(unittest.TestCase):
    def test_activity_aliases(self):
        record = ActivityRecord.from_mapping(
            {
                "activity_id": "abc",
                "date": "2026-01-01",
                "activity_type": "running",
                "duration": 1800.0,
                "averageHR": 140,
            }
        )
        self.assertEqual("running", record.type)
        self.assertEqual(1800.0, record.duration_seconds)
        self.assertEqual(140, record.avg_hr)


class ManualTrackingRecordTests(unittest.TestCase):
    def test_manual_fields(self):
        record = ManualTrackingRecord.from_mapping(
            {"date": "2026-01-01", "energy": 7, "calm": 8, "supplements": "D3"}
        )
        self.assertEqual(7, record.energy)
        self.assertEqual(8, record.calm)
        self.assertEqual("D3", record.supplements)


if __name__ == "__main__":
    unittest.main()

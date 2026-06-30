import sqlite3
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401

from garmin_health_etl.models import (  # noqa: E402
    ActivityRecord,
    GarminDataRecord,
    ManualTrackingRecord,
)
from garmin_health_etl.store import SQLiteStore  # noqa: E402


class StoreTests(unittest.TestCase):
    def test_upsert_and_fetch_all_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "h.db")
            store.initialize()

            store.upsert_garmin_data(
                [GarminDataRecord.from_mapping({"date": "2026-01-01", "steps": 8000})]
            )
            store.upsert_activities(
                [ActivityRecord.from_mapping({"activity_id": "a1", "date": "2026-01-01"})]
            )
            store.upsert_manual_tracking(
                [ManualTrackingRecord.from_mapping({"date": "2026-01-01", "energy": 7})]
            )

            g = store.fetch_garmin_data()
            self.assertEqual(1, len(g))
            self.assertEqual(8000, g[0]["steps"])
            self.assertEqual(1, len(store.fetch_activities()))
            self.assertEqual(1, len(store.fetch_manual_tracking()))

            summary = store.summary()
            self.assertEqual(1, summary.total_records)
            self.assertEqual(1, summary.activities_count)
            self.assertEqual(1, summary.manual_tracking_count)

    def test_upsert_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "h.db")
            store.initialize()
            rec = GarminDataRecord.from_mapping({"date": "2026-01-01", "steps": 1})
            store.upsert_garmin_data([rec])
            rec2 = GarminDataRecord.from_mapping({"date": "2026-01-01", "steps": 2})
            store.upsert_garmin_data([rec2])
            rows = store.fetch_garmin_data()
            self.assertEqual(1, len(rows))
            self.assertEqual(2, rows[0]["steps"])

    def test_join_on_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "h.db")
            store.initialize()
            store.upsert_garmin_data(
                [GarminDataRecord.from_mapping({"date": "2026-01-01", "hrv_last_night": 45})]
            )
            store.upsert_manual_tracking(
                [ManualTrackingRecord.from_mapping({"date": "2026-01-01", "energy": 9})]
            )
            joined = store.fetch_joined()
            self.assertEqual(1, len(joined))
            self.assertEqual(45, joined[0]["hrv_last_night"])
            self.assertEqual(9, joined[0]["m_energy"])

    def test_migration_from_legacy_schema_backfills(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE garmin_data ("
                "date TEXT PRIMARY KEY, hrv_avg REAL, rhr INTEGER, "
                "body_battery_recharge INTEGER)"
            )
            conn.execute(
                "INSERT INTO garmin_data (date, hrv_avg, rhr, body_battery_recharge) "
                "VALUES ('2025-12-31', 44.0, 52, 60)"
            )
            conn.commit()
            conn.close()

            store = SQLiteStore(db)
            store.initialize()  # should add new columns and backfill renamed ones
            rows = store.fetch_garmin_data()
            self.assertEqual(1, len(rows))
            self.assertEqual(44.0, rows[0]["hrv_last_night"])
            self.assertEqual(52, rows[0]["resting_hr"])
            self.assertEqual(60, rows[0]["bb_charged_overnight"])


if __name__ == "__main__":
    unittest.main()

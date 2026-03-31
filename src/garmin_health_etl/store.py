"""SQLite storage layer for Garmin Health ETL."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional

from .models import GarminDataRecord, Summary

GARMIN_DATA_COLUMNS = (
    "date",
    "bed_time",
    "wake_time",
    "sleep_score",
    "hrv_avg",
    "rhr",
    "body_battery_recharge",
    "wake_ups",
    "restlessness_score",
)

PSV_HEADER = (
    "Date|Bed Time|Wake Time|Garmin Sleep Score|Garmin HRV|Garmin RHR|"
    "Garmin Body Battery Recharge|Garmin Wake-ups|Garmin Restlessness Score"
)


class SQLiteStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS garmin_data (
                    date TEXT PRIMARY KEY,
                    bed_time TEXT,
                    wake_time TEXT,
                    sleep_score INTEGER,
                    hrv_avg REAL,
                    rhr INTEGER,
                    body_battery_recharge INTEGER,
                    wake_ups INTEGER,
                    restlessness_score TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_tracking (
                    date TEXT PRIMARY KEY,
                    energy_am INTEGER,
                    energy_pm INTEGER,
                    mood_am INTEGER,
                    mood_pm INTEGER,
                    stress_level INTEGER,
                    appetite_level INTEGER,
                    supplements_am TEXT,
                    supplements_pm TEXT,
                    meals TEXT,
                    skin_condition TEXT,
                    sinus_allergy TEXT,
                    inflammation_joint_pain TEXT,
                    digestive_notes TEXT,
                    bowel_movements TEXT,
                    exercise TEXT,
                    other_notes TEXT,
                    notable_stressor TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS collection_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    data_type TEXT,
                    success BOOLEAN,
                    error_message TEXT,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def upsert_garmin_data(self, records: Iterable[GarminDataRecord]) -> int:
        rows = [
            (
                record.date,
                record.bed_time,
                record.wake_time,
                record.sleep_score,
                record.hrv_avg,
                record.rhr,
                record.body_battery_recharge,
                record.wake_ups,
                record.restlessness_score,
            )
            for record in records
        ]
        if not rows:
            return 0

        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR REPLACE INTO garmin_data
                (date, bed_time, wake_time, sleep_score, hrv_avg, rhr,
                 body_battery_recharge, wake_ups, restlessness_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def fetch_garmin_data(self) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT date, bed_time, wake_time, sleep_score, hrv_avg, rhr,
                       body_battery_recharge, wake_ups, restlessness_score
                FROM garmin_data
                ORDER BY date
                """
            )
            return cursor.fetchall()

    def log_collection(
        self,
        date: str,
        data_type: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO collection_log (date, data_type, success, error_message)
                VALUES (?, ?, ?, ?)
                """,
                (date, data_type, success, error_message),
            )

    def summary(self) -> Summary:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM garmin_data")
            total_records = int(cursor.fetchone()[0])

            cursor.execute("SELECT MIN(date), MAX(date) FROM garmin_data")
            date_range_row = cursor.fetchone()
            date_range = (date_range_row[0], date_range_row[1])

            cursor.execute("SELECT COUNT(*) FROM garmin_data WHERE sleep_score IS NULL")
            missing_sleep = int(cursor.fetchone()[0])

            cursor.execute("SELECT COUNT(*) FROM garmin_data WHERE hrv_avg IS NULL")
            missing_hrv = int(cursor.fetchone()[0])

            cursor.execute(
                "SELECT COUNT(*) FROM garmin_data WHERE body_battery_recharge IS NULL"
            )
            missing_body_battery = int(cursor.fetchone()[0])

        return Summary(
            total_records=total_records,
            date_range=date_range,
            missing_sleep_scores=missing_sleep,
            missing_hrv=missing_hrv,
            missing_body_battery=missing_body_battery,
        )

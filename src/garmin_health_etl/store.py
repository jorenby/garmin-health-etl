"""SQLite storage layer for Garmin Health ETL.

The schema is generated from the field specs in :mod:`garmin_health_etl.models`,
so adding a metric is a one-line change in one place. ``initialize`` also runs a
small idempotent migration: it adds any newly-introduced columns to an existing
database and backfills the three columns that were renamed from the original
schema (hrv_avg -> hrv_last_night, rhr -> resting_hr,
body_battery_recharge -> bb_charged_overnight).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional

from .models import (
    ACTIVITY_SPEC,
    GARMIN_DATA_SPEC,
    MANUAL_TRACKING_SPEC,
    SQL_TYPES,
    ActivityRecord,
    GarminDataRecord,
    ManualTrackingRecord,
    Summary,
    spec_field_names,
)

GARMIN_DATA_COLUMNS = spec_field_names(GARMIN_DATA_SPEC)
ACTIVITY_COLUMNS = spec_field_names(ACTIVITY_SPEC)
MANUAL_TRACKING_COLUMNS = spec_field_names(MANUAL_TRACKING_SPEC)

# Frozen legacy PSV contract: header text and column order must not change.
PSV_COLUMNS = (
    "date",
    "bed_time",
    "wake_time",
    "sleep_score",
    "hrv_last_night",
    "resting_hr",
    "bb_charged_overnight",
    "wake_ups",
    "restlessness_score",
)
PSV_HEADER = (
    "Date|Bed Time|Wake Time|Garmin Sleep Score|Garmin HRV|Garmin RHR|"
    "Garmin Body Battery Recharge|Garmin Wake-ups|Garmin Restlessness Score"
)

# Columns from the original schema that were renamed; used for backfill.
_RENAMED = {
    "hrv_avg": "hrv_last_night",
    "rhr": "resting_hr",
    "body_battery_recharge": "bb_charged_overnight",
}


def _column_defs(spec, primary_key: str) -> str:
    parts = []
    for field in spec:
        sqltype = SQL_TYPES[field.kind]
        if field.name == primary_key:
            parts.append(f"{field.name} {sqltype} PRIMARY KEY")
        else:
            parts.append(f"{field.name} {sqltype}")
    return ",\n                    ".join(parts)


class SQLiteStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -- schema -------------------------------------------------------------- #
    def initialize(self) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS garmin_data (
                    {_column_defs(GARMIN_DATA_SPEC, "date")},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS activities (
                    {_column_defs(ACTIVITY_SPEC, "activity_id")},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS manual_tracking (
                    {_column_defs(MANUAL_TRACKING_SPEC, "date")},
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

            # Idempotent migration for databases created before a column existed.
            self._ensure_columns(cursor, "garmin_data", GARMIN_DATA_SPEC)
            self._ensure_columns(cursor, "activities", ACTIVITY_SPEC)
            self._ensure_columns(cursor, "manual_tracking", MANUAL_TRACKING_SPEC)
            self._backfill_renamed(cursor)

    @staticmethod
    def _existing_columns(cursor, table: str) -> set:
        cursor.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}

    def _ensure_columns(self, cursor, table: str, spec) -> None:
        existing = self._existing_columns(cursor, table)
        for field in spec:
            if field.name not in existing:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {field.name} {SQL_TYPES[field.kind]}"
                )

    def _backfill_renamed(self, cursor) -> None:
        existing = self._existing_columns(cursor, "garmin_data")
        for old, new in _RENAMED.items():
            if old in existing and new in existing:
                cursor.execute(
                    f"UPDATE garmin_data SET {new} = {old} "
                    f"WHERE {new} IS NULL AND {old} IS NOT NULL"
                )

    # -- upserts ------------------------------------------------------------- #
    def _upsert(self, table: str, columns, records, to_row) -> int:
        rows = [to_row(record) for record in records]
        if not rows:
            return 0
        placeholders = ", ".join("?" for _ in columns)
        collist = ", ".join(columns)
        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                rows,
            )
        return len(rows)

    def upsert_garmin_data(self, records: Iterable[GarminDataRecord]) -> int:
        return self._upsert(
            "garmin_data",
            GARMIN_DATA_COLUMNS,
            records,
            lambda r: tuple(getattr(r, c) for c in GARMIN_DATA_COLUMNS),
        )

    def upsert_activities(self, records: Iterable[ActivityRecord]) -> int:
        return self._upsert(
            "activities",
            ACTIVITY_COLUMNS,
            records,
            lambda r: tuple(getattr(r, c) for c in ACTIVITY_COLUMNS),
        )

    def upsert_manual_tracking(self, records: Iterable[ManualTrackingRecord]) -> int:
        return self._upsert(
            "manual_tracking",
            MANUAL_TRACKING_COLUMNS,
            records,
            lambda r: tuple(getattr(r, c) for c in MANUAL_TRACKING_COLUMNS),
        )

    # -- fetches ------------------------------------------------------------- #
    def fetch_garmin_data(self) -> List[sqlite3.Row]:
        cols = ", ".join(GARMIN_DATA_COLUMNS)
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {cols} FROM garmin_data ORDER BY date")
            return cursor.fetchall()

    def fetch_activities(self) -> List[sqlite3.Row]:
        cols = ", ".join(ACTIVITY_COLUMNS)
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {cols} FROM activities ORDER BY date, start_time")
            return cursor.fetchall()

    def fetch_manual_tracking(self) -> List[sqlite3.Row]:
        cols = ", ".join(MANUAL_TRACKING_COLUMNS)
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {cols} FROM manual_tracking ORDER BY date")
            return cursor.fetchall()

    def fetch_joined(self) -> List[sqlite3.Row]:
        """garmin_data LEFT JOIN manual_tracking on date.

        Manual columns are aliased ``m_<column>`` to avoid clashing with the
        Garmin columns (e.g. both could conceivably carry overlapping names).
        """
        g_cols = ", ".join(f"g.{c}" for c in GARMIN_DATA_COLUMNS)
        m_cols = ", ".join(
            f"m.{c} AS m_{c}" for c in MANUAL_TRACKING_COLUMNS if c != "date"
        )
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT {g_cols}, {m_cols}
                FROM garmin_data g
                LEFT JOIN manual_tracking m ON g.date = m.date
                ORDER BY g.date
                """
            )
            return cursor.fetchall()

    # -- misc ---------------------------------------------------------------- #
    def log_collection(
        self,
        date: str,
        data_type: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
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

            cursor.execute(
                "SELECT COUNT(*) FROM garmin_data WHERE hrv_last_night IS NULL"
            )
            missing_hrv = int(cursor.fetchone()[0])

            cursor.execute(
                "SELECT COUNT(*) FROM garmin_data WHERE bb_charged_overnight IS NULL"
            )
            missing_body_battery = int(cursor.fetchone()[0])

            cursor.execute("SELECT COUNT(*) FROM activities")
            activities_count = int(cursor.fetchone()[0])

            cursor.execute("SELECT COUNT(*) FROM manual_tracking")
            manual_tracking_count = int(cursor.fetchone()[0])

        return Summary(
            total_records=total_records,
            date_range=date_range,
            missing_sleep_scores=missing_sleep,
            missing_hrv=missing_hrv,
            missing_body_battery=missing_body_battery,
            activities_count=activities_count,
            manual_tracking_count=manual_tracking_count,
        )

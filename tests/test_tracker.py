import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401

from garmin_health_etl.tracker import (  # noqa: E402
    load_tracker_csv,
    map_headers,
    parse_date,
    parse_rating,
)


class HeaderMappingTests(unittest.TestCase):
    def test_maps_verbose_form_headers(self):
        headers = [
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
        mapping = map_headers(headers)
        self.assertEqual("Date", mapping["date"])
        self.assertEqual("Perceived energy (1-10)", mapping["energy"])
        self.assertEqual("Calm (1-10)", mapping["calm"])
        self.assertNotIn("stress", mapping)
        self.assertEqual("Other notes", mapping["other_notes"])

    def test_maps_legacy_stress_header(self):
        mapping = map_headers(["Date", "Stress Level (peak, 1-10)", "Energy AM (1-10)"])
        self.assertIn("stress", mapping)
        self.assertNotIn("calm", mapping)


class ParsingTests(unittest.TestCase):
    def test_parse_rating_handles_ranges_and_clamping(self):
        self.assertEqual(7, parse_rating("7"))
        self.assertEqual(6, parse_rating("5-6"))  # averaged then rounded
        self.assertEqual(8, parse_rating("8 - good"))
        self.assertIsNone(parse_rating(""))
        self.assertEqual(10, parse_rating("12"))  # clamp high

    def test_parse_date_formats(self):
        self.assertEqual("2026-06-24", parse_date("2026-06-24"))
        self.assertEqual("2026-06-24", parse_date("6/24/2026"))
        self.assertEqual("2026-06-24", parse_date("6/24/2026 21:30:00"))
        self.assertIsNone(parse_date(""))


class PolarityTests(unittest.TestCase):
    def test_calm_taken_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.csv"
            path.write_text(
                "Date,Calm (1-10),Perceived energy (1-10)\n2026-06-25,8,7\n",
                encoding="utf-8",
            )
            records = load_tracker_csv(path)
            self.assertEqual(1, len(records))
            self.assertEqual(8, records[0].calm)

    def test_legacy_stress_is_inverted_to_calm(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.csv"
            path.write_text(
                "Date,Stress Level (peak),Energy AM (1-10)\n2025-08-01,8,5\n",
                encoding="utf-8",
            )
            records = load_tracker_csv(path)
            self.assertEqual(1, len(records))
            self.assertEqual(11 - 8, records[0].calm)  # inverted
            self.assertEqual(5, records[0].energy)

    def test_rows_without_date_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.csv"
            path.write_text(
                "Date,Calm (1-10)\n2026-06-25,8\n,5\n",
                encoding="utf-8",
            )
            self.assertEqual(1, len(load_tracker_csv(path)))


if __name__ == "__main__":
    unittest.main()

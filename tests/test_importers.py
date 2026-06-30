import json
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401

from garmin_health_etl.importers import load_payload, load_records  # noqa: E402


class ImporterTests(unittest.TestCase):
    def _write(self, tmp, name, text):
        path = Path(tmp) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_legacy_single_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "x.json", json.dumps({"date": "2026-01-01"}))
            records = load_records(path)
            self.assertEqual(1, len(records))
            self.assertEqual("2026-01-01", records[0].date)

    def test_legacy_records_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp, "x.json", json.dumps({"records": [{"date": "2026-01-01"}]})
            )
            self.assertEqual(1, len(load_records(path)))

    def test_ndjson(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                "x.ndjson",
                '{"date":"2026-01-01"}\n{"date":"2026-01-02"}\n',
            )
            self.assertEqual(2, len(load_records(path)))

    def test_typed_payload_routes_all_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "garmin_data": [{"date": "2026-01-01"}],
                "activities": [{"activity_id": "a1", "date": "2026-01-01"}],
                "manual_tracking": [{"date": "2026-01-01", "energy": 7}],
            }
            path = self._write(tmp, "typed.json", json.dumps(payload))
            result = load_payload(path)
            self.assertEqual(1, len(result["garmin_data"]))
            self.assertEqual(1, len(result["activities"]))
            self.assertEqual(1, len(result["manual_tracking"]))

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_records("/no/such/file.json")


if __name__ == "__main__":
    unittest.main()

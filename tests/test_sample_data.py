import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401

from garmin_health_etl.sample_data import generate, write_sample  # noqa: E402


class SampleDataTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self):
        a, ta = generate(days=30, seed=7)
        b, tb = generate(days=30, seed=7)
        self.assertEqual(a, b)
        self.assertEqual(ta, tb)

    def test_different_seed_differs(self):
        a, _ = generate(days=30, seed=1)
        b, _ = generate(days=30, seed=2)
        self.assertNotEqual(a, b)

    def test_structure_and_ranges(self):
        payload, tracker = generate(days=60, seed=3)
        self.assertEqual(60, len(payload["garmin_data"]))
        self.assertTrue(payload["activities"])  # at least one workout
        for day in payload["garmin_data"]:
            self.assertIn("date", day)
            self.assertTrue(1 <= day["sleep_score"] <= 100)
        for row in tracker:
            self.assertTrue(1 <= row["Perceived energy (1-10)"] <= 10)

    def test_write_sample_creates_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_sample(tmp, days=20, seed=5)
            self.assertEqual(2, len(paths))
            for path in paths:
                self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()

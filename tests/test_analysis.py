import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401

try:
    import matplotlib  # noqa: F401
    import numpy  # noqa: F401
    import pandas  # noqa: F401

    HAVE_ANALYSIS_DEPS = True
except ImportError:
    HAVE_ANALYSIS_DEPS = False

from garmin_health_etl.models import (  # noqa: E402
    ActivityRecord,
    GarminDataRecord,
)
from garmin_health_etl.sample_data import generate  # noqa: E402
from garmin_health_etl.store import SQLiteStore  # noqa: E402
from garmin_health_etl.tracker import map_headers, rows_to_records  # noqa: E402


def _build_store(db_path, days=120, seed=42):
    payload, tracker_rows = generate(days=days, seed=seed)
    store = SQLiteStore(db_path)
    store.initialize()
    store.upsert_garmin_data(
        [GarminDataRecord.from_mapping(d) for d in payload["garmin_data"]]
    )
    store.upsert_activities(
        [ActivityRecord.from_mapping(a) for a in payload["activities"]]
    )
    if tracker_rows:
        mapping = map_headers(list(tracker_rows[0].keys()))
        store.upsert_manual_tracking(rows_to_records(tracker_rows, mapping))
    return store


@unittest.skipUnless(HAVE_ANALYSIS_DEPS, "requires the [analysis] extra")
class AnalysisTests(unittest.TestCase):
    def test_correlation_signs_match_design(self):
        from garmin_health_etl.analysis import _load_frame, spearman

        with tempfile.TemporaryDirectory() as tmp:
            store = _build_store(Path(tmp) / "h.db")
            df = _load_frame(store)

            calm_energy, n = spearman(df["calm"], df["energy"])
            self.assertGreater(n, 50)
            self.assertGreater(calm_energy, 0.4)  # designed strong positive

            hrv_energy, _ = spearman(df["hrv"], df["energy"])
            self.assertLess(abs(hrv_energy), 0.25)  # recovery ~ energy near zero

    def test_run_analysis_writes_report_and_charts(self):
        from garmin_health_etl.analysis import run_analysis

        with tempfile.TemporaryDirectory() as tmp:
            store = _build_store(Path(tmp) / "h.db")
            report = run_analysis(
                store, output_path=str(Path(tmp) / "report.md"),
                charts_dir=str(Path(tmp) / "charts"),
            )
            text = Path(report).read_text(encoding="utf-8")
            self.assertIn("Health analysis report", text)
            self.assertIn("Same-day correlations", text)
            self.assertTrue(list((Path(tmp) / "charts").glob("*.png")))

    def test_report_command_imports_and_analyzes(self):
        from garmin_health_etl import cli
        from garmin_health_etl.sample_data import write_sample

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_sample(tmp_path, days=60, seed=9)
            exit_code = cli.main(
                [
                    "report",
                    "--db",
                    str(tmp_path / "h.db"),
                    "--garmin",
                    str(tmp_path / "sample_garmin.json"),
                    "--tracker",
                    str(tmp_path / "sample_tracker.csv"),
                    "--output",
                    str(tmp_path / "report.md"),
                    "--charts-dir",
                    str(tmp_path / "charts"),
                ]
            )
            self.assertEqual(0, exit_code)
            self.assertIn(
                "Same-day correlations",
                (tmp_path / "report.md").read_text(encoding="utf-8"),
            )

    def test_empty_db_produces_graceful_report(self):
        from garmin_health_etl.analysis import run_analysis

        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "empty.db")
            store.initialize()
            report = run_analysis(
                store, output_path=str(Path(tmp) / "r.md"), make_charts=False
            )
            self.assertIn("No data", Path(report).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

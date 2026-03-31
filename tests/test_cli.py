import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from garmin_health_etl import cli  # noqa: E402
from garmin_health_etl.importers import load_records  # noqa: E402


class ImporterTests(unittest.TestCase):
    def test_load_records_accepts_ndjson(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "sample.ndjson"
            input_path.write_text(
                '{"date":"2026-03-01","sleep_score":80}\n'
                '{"date":"2026-03-02","sleep_score":81}\n',
                encoding="utf-8",
            )

            records = load_records(input_path)

            self.assertEqual(2, len(records))
            self.assertEqual("2026-03-01", records[0].date)
            self.assertEqual(81, records[1].sleep_score)


class CLITests(unittest.TestCase):
    def test_import_summary_and_export_psv(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.json"
            db_path = tmp_path / "health.db"
            output_path = tmp_path / "health.psv"

            input_path.write_text(
                json.dumps(
                    [
                        {
                            "date": "2026-02-28",
                            "bed_time": "22:30",
                            "wake_time": "06:15",
                            "sleep_score": 82,
                            "hrv_avg": 41.5,
                            "rhr": 54,
                            "body_battery_recharge": 68,
                            "wake_ups": 1,
                            "restlessness_score": "LOW",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            import_buffer = io.StringIO()
            with redirect_stdout(import_buffer):
                exit_code = cli.main(
                    [
                        "import-json",
                        "--input",
                        str(input_path),
                        "--db",
                        str(db_path),
                        "--source",
                        "garmin-cli",
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertIn("Imported 1 records", import_buffer.getvalue())

            summary_buffer = io.StringIO()
            with redirect_stdout(summary_buffer):
                exit_code = cli.main(
                    ["summary", "--db", str(db_path), "--format", "json"]
                )

            self.assertEqual(0, exit_code)
            summary_payload = json.loads(summary_buffer.getvalue())
            self.assertEqual(1, summary_payload["total_records"])
            self.assertEqual("2026-02-28", summary_payload["date_range"]["start"])
            self.assertEqual("2026-02-28", summary_payload["date_range"]["end"])

            export_buffer = io.StringIO()
            with redirect_stdout(export_buffer):
                exit_code = cli.main(
                    ["export-psv", "--db", str(db_path), "--output", str(output_path)]
                )

            self.assertEqual(0, exit_code)
            self.assertTrue(output_path.exists())
            psv_lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                "Date|Bed Time|Wake Time|Garmin Sleep Score|Garmin HRV|Garmin RHR|"
                "Garmin Body Battery Recharge|Garmin Wake-ups|"
                "Garmin Restlessness Score",
                psv_lines[0],
            )
            self.assertEqual(
                "2026-02-28|22:30|06:15|82|41.5|54|68|1|LOW",
                psv_lines[1],
            )

    def test_upstream_saves_stdout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "upstream.txt"

            stdout_buffer = io.StringIO()
            with redirect_stdout(stdout_buffer):
                exit_code = cli.main(
                    [
                        "upstream",
                        "--output",
                        str(output_path),
                        "--",
                        sys.executable,
                        "-c",
                        'print("hello from upstream")',
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertTrue(output_path.exists())
            self.assertEqual(
                "hello from upstream\n",
                output_path.read_text(encoding="utf-8"),
            )
            self.assertIn("Saved upstream stdout", stdout_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"


class EndToEndCLITests(unittest.TestCase):
    def test_import_summary_export_flow_via_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "sample.json"
            db_path = tmp_path / "health.db"
            output_path = tmp_path / "health.psv"

            input_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "date": "2026-03-01",
                                "bed_time": "22:45",
                                "wake_time": "06:30",
                                "sleep_score": 85,
                                "hrv_avg": 44.0,
                                "rhr": 53,
                                "body_battery_recharge": 70,
                                "wake_ups": 2,
                                "restlessness_score": "MEDIUM",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            existing_pythonpath = env.get("PYTHONPATH")
            if existing_pythonpath:
                env["PYTHONPATH"] = str(SRC_PATH) + os.pathsep + existing_pythonpath
            else:
                env["PYTHONPATH"] = str(SRC_PATH)

            import_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "garmin_health_etl.cli",
                    "import-json",
                    "--input",
                    str(input_path),
                    "--db",
                    str(db_path),
                    "--source",
                    "garmin-cli",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env,
            )

            self.assertEqual(0, import_result.returncode, import_result.stderr)
            self.assertIn("Imported 1 garmin_data", import_result.stdout)

            summary_result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "garmin_etl.py"),
                    "summary",
                    "--db",
                    str(db_path),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env,
            )

            self.assertEqual(0, summary_result.returncode, summary_result.stderr)
            summary_payload = json.loads(summary_result.stdout)
            self.assertEqual(1, summary_payload["total_records"])
            self.assertEqual("2026-03-01", summary_payload["date_range"]["start"])

            export_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "garmin_health_etl.cli",
                    "export-psv",
                    "--db",
                    str(db_path),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                env=env,
            )

            self.assertEqual(0, export_result.returncode, export_result.stderr)
            self.assertTrue(output_path.exists())
            exported_lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(2, len(exported_lines))
            self.assertIn("2026-03-01|22:45|06:30|85|44.0|53|70|2|MEDIUM", exported_lines[1])


if __name__ == "__main__":
    unittest.main()

"""Command-line interface for Garmin Health ETL."""

from __future__ import annotations

import argparse
import json
import sys

from .exporters import export_csv, export_psv
from .importers import load_payload
from .store import SQLiteStore
from .upstream import run_upstream


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="garmin-health-etl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- extract ------------------------------------------------------------- #
    extract_parser = subparsers.add_parser(
        "extract",
        help="Pull daily wellness + activities from Garmin Connect to JSON",
    )
    extract_parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    extract_parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    extract_parser.add_argument(
        "--output", help="JSON output path (default: stdout)"
    )
    extract_parser.add_argument(
        "--no-activities", action="store_true", help="Skip per-workout activities"
    )
    extract_parser.set_defaults(handler=handle_extract)

    # -- import-json --------------------------------------------------------- #
    import_parser = subparsers.add_parser(
        "import-json",
        help="Import normalized JSON or NDJSON records into SQLite",
    )
    import_parser.add_argument("--input", required=True, help="Path to JSON or NDJSON")
    import_parser.add_argument("--db", required=True, help="SQLite database path")
    import_parser.add_argument(
        "--source",
        default="unknown",
        help="Source label for collection_log entries",
    )
    import_parser.set_defaults(handler=handle_import_json)

    # -- import-tracker ------------------------------------------------------ #
    tracker_parser = subparsers.add_parser(
        "import-tracker",
        help="Import Daily Health Tracker (Google Form) CSV into manual_tracking",
    )
    tracker_parser.add_argument("--input", required=True, help="Form responses CSV")
    tracker_parser.add_argument("--db", required=True, help="SQLite database path")
    tracker_parser.set_defaults(handler=handle_import_tracker)

    # -- export-psv ---------------------------------------------------------- #
    export_parser = subparsers.add_parser(
        "export-psv",
        help="Export garmin_data rows to the legacy PSV format",
    )
    export_parser.add_argument("--db", required=True, help="SQLite database path")
    export_parser.add_argument("--output", required=True, help="PSV output file")
    export_parser.set_defaults(handler=handle_export_psv)

    # -- export-csv ---------------------------------------------------------- #
    export_csv_parser = subparsers.add_parser(
        "export-csv",
        help="Export the full garmin_data table (all columns) to CSV",
    )
    export_csv_parser.add_argument("--db", required=True, help="SQLite database path")
    export_csv_parser.add_argument("--output", required=True, help="CSV output file")
    export_csv_parser.set_defaults(handler=handle_export_csv)

    # -- analyze ------------------------------------------------------------- #
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Compute correlations/trends and write a markdown report + charts",
    )
    analyze_parser.add_argument("--db", required=True, help="SQLite database path")
    analyze_parser.add_argument(
        "--output", default="report.md", help="Markdown report path"
    )
    analyze_parser.add_argument(
        "--charts-dir", help="Directory for chart PNGs (default: alongside report)"
    )
    analyze_parser.add_argument(
        "--no-charts", action="store_true", help="Skip chart generation"
    )
    analyze_parser.set_defaults(handler=handle_analyze)

    # -- generate-sample ----------------------------------------------------- #
    sample_parser = subparsers.add_parser(
        "generate-sample",
        help="Generate a synthetic dataset (JSON + tracker CSV) for demos/tests",
    )
    sample_parser.add_argument(
        "--output-dir", required=True, help="Directory to write sample files"
    )
    sample_parser.add_argument(
        "--days", type=int, default=120, help="Number of days to synthesize"
    )
    sample_parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (deterministic output)"
    )
    sample_parser.set_defaults(handler=handle_generate_sample)

    # -- summary ------------------------------------------------------------- #
    summary_parser = subparsers.add_parser(
        "summary",
        help="Show a summary of records in the SQLite database",
    )
    summary_parser.add_argument("--db", required=True, help="SQLite database path")
    summary_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Summary output format",
    )
    summary_parser.set_defaults(handler=handle_summary)

    # -- upstream ------------------------------------------------------------ #
    upstream_parser = subparsers.add_parser(
        "upstream",
        help="Run an external upstream command and optionally save stdout",
    )
    upstream_parser.add_argument(
        "--output",
        help="Optional file path to save upstream stdout",
    )
    upstream_parser.add_argument(
        "upstream_command",
        nargs=argparse.REMAINDER,
        help="Command to execute after '--'",
    )
    upstream_parser.set_defaults(handler=handle_upstream)

    return parser


def handle_extract(args: argparse.Namespace) -> int:
    # Lazy import: python-garminconnect is an optional [garmin] extra.
    from .garmin_source import extract_to_payload

    payload = extract_to_payload(
        args.start, args.end, include_activities=not args.no_activities
    )
    text = json.dumps(payload, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
        n_days = len(payload.get("garmin_data", []))
        n_act = len(payload.get("activities", []))
        print(f"Wrote {n_days} day(s) and {n_act} activity(ies) to {args.output}")
    else:
        sys.stdout.write(text + "\n")
    return 0


def handle_import_json(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    store.initialize()
    payload = load_payload(args.input)

    inserted = store.upsert_garmin_data(payload["garmin_data"])
    activities = store.upsert_activities(payload["activities"])
    manual = store.upsert_manual_tracking(payload["manual_tracking"])

    store.log_collection(
        date="bulk-import",
        data_type=f"import_json:{args.source}",
        success=True,
    )
    print(
        f"Imported {inserted} garmin_data, {activities} activities, "
        f"{manual} manual_tracking into {store.db_path}"
    )
    return 0


def handle_import_tracker(args: argparse.Namespace) -> int:
    from .tracker import load_tracker_csv

    store = SQLiteStore(args.db)
    store.initialize()
    records = load_tracker_csv(args.input)
    inserted = store.upsert_manual_tracking(records)
    store.log_collection(
        date="bulk-import", data_type="import_tracker", success=True
    )
    print(f"Imported {inserted} manual_tracking rows into {store.db_path}")
    return 0


def handle_export_psv(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    store.initialize()
    destination = export_psv(store, args.output)
    print(f"Wrote PSV export to {destination}")
    return 0


def handle_export_csv(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    store.initialize()
    destination = export_csv(store, args.output)
    print(f"Wrote CSV export to {destination}")
    return 0


def handle_analyze(args: argparse.Namespace) -> int:
    from .analysis import run_analysis

    store = SQLiteStore(args.db)
    store.initialize()
    report_path = run_analysis(
        store,
        output_path=args.output,
        charts_dir=args.charts_dir,
        make_charts=not args.no_charts,
    )
    print(f"Wrote analysis report to {report_path}")
    return 0


def handle_generate_sample(args: argparse.Namespace) -> int:
    from .sample_data import write_sample

    paths = write_sample(args.output_dir, days=args.days, seed=args.seed)
    print("Wrote sample files:")
    for path in paths:
        print(f"  {path}")
    return 0


def handle_summary(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    store.initialize()
    summary = store.summary()

    if args.format == "json":
        print(json.dumps(summary.as_dict(), indent=2))
        return 0

    start_date, end_date = summary.date_range
    print(f"Total records: {summary.total_records}")
    print(f"Date range: {start_date or '-'} to {end_date or '-'}")
    print(f"Missing sleep scores: {summary.missing_sleep_scores}")
    print(f"Missing HRV: {summary.missing_hrv}")
    print(f"Missing Body Battery: {summary.missing_body_battery}")
    print(f"Activities: {summary.activities_count}")
    print(f"Manual tracking rows: {summary.manual_tracking_count}")
    return 0


def handle_upstream(args: argparse.Namespace) -> int:
    command = list(args.upstream_command)
    if command and command[0] == "--":
        command = command[1:]

    if not command:
        raise SystemExit("upstream requires a command after '--'")

    result = run_upstream(command, args.output)

    if args.output:
        print(f"Saved upstream stdout to {args.output}")
    else:
        sys.stdout.write(result.stdout)

    if result.stderr:
        sys.stderr.write(result.stderr)

    return result.returncode


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

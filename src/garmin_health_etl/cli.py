"""Command-line interface for Garmin Health ETL."""

from __future__ import annotations

import argparse
import json
import sys

from .exporters import export_psv
from .importers import load_records
from .store import SQLiteStore
from .upstream import run_upstream


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="garmin-health-etl")
    subparsers = parser.add_subparsers(dest="command", required=True)

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

    export_parser = subparsers.add_parser(
        "export-psv",
        help="Export garmin_data rows to PSV",
    )
    export_parser.add_argument("--db", required=True, help="SQLite database path")
    export_parser.add_argument("--output", required=True, help="PSV output file")
    export_parser.set_defaults(handler=handle_export_psv)

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


def handle_import_json(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    store.initialize()
    records = load_records(args.input)
    inserted = store.upsert_garmin_data(records)
    store.log_collection(
        date="bulk-import",
        data_type=f"import_json:{args.source}",
        success=True,
    )
    print(f"Imported {inserted} records into {store.db_path}")
    return 0


def handle_export_psv(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    store.initialize()
    destination = export_psv(store, args.output)
    print(f"Wrote PSV export to {destination}")
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

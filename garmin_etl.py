#!/usr/bin/env python3
"""Compatibility wrapper for the packaged Garmin Health ETL CLI."""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    repo_root = Path(__file__).resolve().parent
    src_path = repo_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


def main(argv=None) -> int:
    _bootstrap_src_path()

    from garmin_health_etl.cli import main as cli_main

    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print(
            "garmin_etl.py is a compatibility wrapper. Use 'garmin-health-etl <command>' "
            "or 'python garmin_etl.py <command>'.",
            file=sys.stderr,
        )
        argv = ["--help"]

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

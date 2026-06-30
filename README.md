# Garmin Health ETL

A small, tested Python CLI that imports normalized Garmin health records into SQLite and exports them to PSV (pipe-separated values) for analysis.

It treats `garmin-cli` as an external upstream tool, keeping data collection cleanly separated from storage and export. The intended flow is:

```text
garmin ...  ->  structured export file  ->  garmin-health-etl import-json  ->  garmin-health-etl export-psv
```

## Why this exists

I track my own sleep, HRV, resting heart rate, and recovery to look for patterns over time. This tool gives me a stable, queryable store for that data instead of one-off CSV scrapes — normalized records in SQLite, reproducible PSV exports, and a clear boundary between the upstream collector and my own pipeline.

## Project layout

```text
src/garmin_health_etl/   # package: CLI, importer, exporter, storage
tests/                   # unittest suite
garmin_etl.py            # legacy compatibility shim
pyproject.toml           # project + entrypoint definition
```

## Install

Use [`uv`](https://docs.astral.sh/uv/) as the primary workflow.

Install `uv` first if it is not already available:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then set up the project:

```bash
uv python install 3.12
uv sync
```

The repo pins local development to Python `3.12` via [`.python-version`](.python-version). `uv sync` creates a local virtual environment and installs the `garmin-health-etl` entrypoint defined in [`pyproject.toml`](pyproject.toml).

Run commands through `uv`:

```bash
uv run garmin-health-etl --help
```

If you need a legacy fallback, `python -m pip install -e .` still works. To regenerate the lockfile, run `uv lock` and commit [`uv.lock`](uv.lock) for a stable developer environment.

## Test

```bash
uv run python -m unittest discover -s tests -v
```

## Commands

### `import-json` — import normalized JSON or NDJSON

The importer accepts:

- A JSON object representing one record
- A JSON array of record objects
- A JSON object with a top-level `records` array
- NDJSON where each line is one record object

Supported normalized fields map directly to the `garmin_data` schema: `date`, `bed_time`, `wake_time`, `sleep_score`, `hrv_avg`, `rhr`, `body_battery_recharge`, `wake_ups`, `restlessness_score`.

```bash
uv run garmin-health-etl import-json \
  --input export.json \
  --db garmin_health.db \
  --source garmin-cli
```

### `export-psv` — export to PSV

Preserves the existing PSV header and column order from the legacy script.

```bash
uv run garmin-health-etl export-psv \
  --db garmin_health.db \
  --output garmin_data.psv
```

### `summary` — show a summary

```bash
uv run garmin-health-etl summary --db garmin_health.db --format text
uv run garmin-health-etl summary --db garmin_health.db --format json
```

### `upstream` — invoke an upstream tool

Runs an external command as a subprocess boundary and can save its stdout without parsing the upstream tool's output.

```bash
uv run garmin-health-etl upstream --output export.json -- garmin export sleep --format json
```

If you omit `--output`, stdout is passed through directly.

## Legacy wrapper

[`garmin_etl.py`](garmin_etl.py) is now only a compatibility shim. It no longer prompts for credentials or dates:

```bash
uv run python garmin_etl.py summary --db garmin_health.db
```

## Storage contract

The SQLite schema creates and preserves three tables:

- `garmin_data` — primary storage table; `export-psv` reads from here
- `manual_tracking`
- `collection_log`

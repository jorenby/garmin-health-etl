# Garmin Health ETL

`garmin-health-etl` is a small Python CLI for storing normalized Garmin health records in SQLite and exporting them to PSV.

The repo now treats `garmin-cli` as an external upstream tool. The intended flow is:

```text
garmin ... -> structured export file -> garmin-health-etl import-json -> garmin-health-etl export-psv
```

## Install

Use `uv` as the primary workflow.

```bash
uv python install 3.12
uv sync
```

The repo pins local development to Python `3.12` via [`.python-version`](/Users/joshuajorenby/code/garmin-health-etl/.python-version). `uv sync` then creates a local virtual environment and installs the `garmin-health-etl` entrypoint from [`pyproject.toml`](/Users/joshuajorenby/code/garmin-health-etl/pyproject.toml).

Then run commands through `uv`:

```bash
uv run garmin-health-etl --help
```

If you need a legacy fallback, `python -m pip install -e .` still works.

If you want a lockfile after installing `uv`, run:

```bash
uv lock
```

Commit [`uv.lock`](/Users/joshuajorenby/code/garmin-health-etl/uv.lock) once it exists. It should be versioned for a stable developer environment.

## Test

Run the built-in test suite with:

```bash
uv run python -m unittest discover -s tests -v
```

## Commands

### Import normalized JSON or NDJSON

The importer accepts:

- A JSON object representing one record
- A JSON array of record objects
- A JSON object with a top-level `records` array
- NDJSON where each line is one record object

Supported normalized fields map directly to the `garmin_data` schema:
`date`, `bed_time`, `wake_time`, `sleep_score`, `hrv_avg`, `rhr`,
`body_battery_recharge`, `wake_ups`, `restlessness_score`

```bash
uv run garmin-health-etl import-json \
  --input export.json \
  --db garmin_health.db \
  --source garmin-cli
```

### Export PSV

This preserves the existing PSV header and column order from the legacy script.

```bash
uv run garmin-health-etl export-psv \
  --db garmin_health.db \
  --output garmin_data.psv
```

### Show a summary

```bash
uv run garmin-health-etl summary --db garmin_health.db --format text
uv run garmin-health-etl summary --db garmin_health.db --format json
```

### Invoke an upstream tool

`upstream` runs an external command as a subprocess boundary and can save stdout without parsing the upstream tool.

```bash
uv run garmin-health-etl upstream --output export.json -- garmin export sleep --format json
```

If you omit `--output`, stdout is passed through directly.

## Legacy Wrapper

[`garmin_etl.py`](/Users/joshuajorenby/code/garmin-health-etl/garmin_etl.py) is now only a compatibility shim. It no longer prompts for credentials or dates. Use it as:

```bash
uv run python garmin_etl.py summary --db garmin_health.db
```

## Storage Contract

The SQLite schema still creates and preserves:

- `garmin_data`
- `manual_tracking`
- `collection_log`

`garmin_data` remains the primary storage table, and `export-psv` reads from that table.

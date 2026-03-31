"""Boundary for invoking external upstream tools like garmin-cli."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_upstream(command, output_path=None):
    if not command:
        raise ValueError("Upstream command is required after '--'")

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(result.stdout, encoding="utf-8")

    return result

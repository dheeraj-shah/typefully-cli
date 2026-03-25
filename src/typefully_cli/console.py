"""Centralized stderr output for status, progress, and warnings."""

from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console as RichConsole
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn


class Console:
    """All non-data output goes through here, always to stderr.

    --quiet suppresses status/progress/warning but NOT error JSON.
    """

    def __init__(self, quiet: bool = False):
        self._quiet = quiet
        self._rich = RichConsole(stderr=True)

    def status(self, msg: str) -> None:
        if not self._quiet:
            self._rich.print(f"[dim]{msg}[/dim]")

    def success(self, msg: str) -> None:
        if not self._quiet:
            self._rich.print(f"[green]{msg}[/green]")

    def warning(self, msg: str) -> None:
        if not self._quiet:
            self._rich.print(f"[yellow]Warning: {msg}[/yellow]")

    def error_json(self, error_dict: dict) -> None:
        """Write structured error JSON as the last line of stderr. Never suppressed."""
        envelope = {"ok": False, "error": error_dict}
        sys.stderr.write(json.dumps(envelope) + "\n")
        sys.stderr.flush()

    def progress(self, description: str = "Processing...") -> Progress:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=self._rich,
            disable=self._quiet,
        )


def write_success(data: Any) -> None:
    """Write success JSON envelope to stdout."""
    envelope = {"ok": True, "data": data}
    sys.stdout.write(json.dumps(envelope, default=str) + "\n")
    sys.stdout.flush()

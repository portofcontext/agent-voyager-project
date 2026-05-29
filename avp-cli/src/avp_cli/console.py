"""Developer-facing output. One pair of rich Consoles with strict discipline.

Results (boards, rendered Commissions) and `--json` go to **stdout** so they
pipe cleanly; progress, status, and diagnostics go to **stderr**. `--json`
output bypasses rich entirely (machine-clean).
"""

from __future__ import annotations

import json as _json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel

# stdout: the result a caller might pipe or capture.
out = Console()
# stderr: progress, status, warnings, errors. Never pollutes piped stdout.
err = Console(stderr=True)


def print_json(obj: Any) -> None:
    """Emit machine-clean JSON to stdout (no rich styling)."""
    sys.stdout.write(_json.dumps(obj, indent=2) + "\n")


def progress(msg: str) -> None:
    """A live progress line on stderr (rich markup allowed in `msg`)."""
    err.print(msg)


def note(msg: str) -> None:
    err.print(f"[dim]{msg}[/dim]")


def warn(msg: str) -> None:
    err.print(f"[yellow]{msg}[/yellow]")


def error_panel(title: str, body: str) -> None:
    err.print(Panel(body, title=title, border_style="red", title_align="left"))


def diag(title: str, body: str, *, style: str = "yellow") -> None:
    """A diagnostic panel on stderr (e.g. the board's failures section)."""
    err.print(Panel(body, title=title, border_style=style, title_align="left"))


def panel(title: str, body: Any, *, style: str = "cyan") -> None:
    out.print(Panel(body, title=title, border_style=style, title_align="left"))

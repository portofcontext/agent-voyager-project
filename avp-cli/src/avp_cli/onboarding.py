"""Onboarding surface: the `avp` welcome / agent-routing screen.

AI-native: a coding agent that runs `avp` (no args) learns the whole loop
without reading source. Evals are JSON config files (no code), so the guidance
is about editing config and driving the CLI. Rendered as rich grids so the
command column aligns and descriptions wrap cleanly in their own column.
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text

from avp_cli import brand

_START = [
    ("avp init", "create an eval to run: pick from the catalog (try 'demo')"),
]

_COMMISSIONS = [
    ("avp commission list", "your commission library"),
    ("avp commission show <id>", "render the Commission an id yields"),
    ("avp commission validate <id>", "check a commission is valid"),
]

_EVAL = [
    ("avp eval run <config>", "run the eval"),
    ("avp eval commissions <config>", "list the commissions an eval references"),
    ("avp eval list", "list recent eval runs"),
    ("avp eval view", "visualize the latest eval"),
    ("avp eval clear", "delete all recorded runs"),
    ("avp show <trajectory.ndjson>", "replay one run (--web for the constellation)"),
]


def _cmd_grid(rows: list[tuple[str, str]]) -> Table:
    grid = Table.grid(padding=(0, 3))
    grid.add_column(no_wrap=True, style=brand.SAIL)  # command
    grid.add_column(overflow="fold", style="#9fb4c2")  # description, wraps in-column
    for cmd, desc in rows:
        grid.add_row(cmd, desc)
    return grid


def welcome() -> Group:
    """The `avp` (no-args) welcome screen as a rich renderable."""

    def section(header: str, rows: list[tuple[str, str]]) -> Group:
        return Group(Text(header, style=f"bold {brand.SKY}"), _cmd_grid(rows), Text())

    return Group(
        section("Start here", _START),
        section("Commissions", _COMMISSIONS),
        section("Evals", _EVAL),
    )

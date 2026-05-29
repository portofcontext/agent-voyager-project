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
    ("avp init", "create an eval to run: pick a benchmark from the catalog"),
]

_COMMISSIONS = [
    ("avp commission create [id]", "build a commission"),
    ("avp commission list", "your commission library"),
    ("avp commission describe <id>", "render the Commission an id yields"),
    ("avp commission check <id>", "check a commission is valid"),
    ("avp commission delete <id>", "remove a commission from your library"),
]

_EVAL = [
    ("avp eval run <config>", "run the eval"),
    ("avp eval list", "list recent eval runs"),
    ("avp eval view", "visualize the latest eval (on agentvoyagerproject.com)"),
    ("avp eval delete <id>", "delete one recorded run (--all for every run)"),
]

_AGENTS = [
    ("avp agent list", "the agents you can run, and whether each is installed"),
    ("avp agent install <name>", "install a prebuilt agent (release, or --binary/--wheel local)"),
    ("avp agent describe <name>", "one agent's capabilities: tools, models, skills, subagents"),
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
        section("Agents", _AGENTS),
        section("Commissions", _COMMISSIONS),
        section("Evals", _EVAL),
    )

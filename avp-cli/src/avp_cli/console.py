"""How avp prints: results to stdout, progress and errors to stderr."""

from typing import Annotated

import typer
from rich.console import Console

out = Console()
err = Console(stderr=True)

verbose: bool = False
"""Set by a command's --verbose."""

VerboseOption = Annotated[
    bool, typer.Option("--verbose", help="Print more about what avp does, to stderr.")
]


def detail(text: str) -> None:
    """Print a line to stderr with --verbose only. Never a secret's value."""
    if verbose:
        err.print(text, style="dim", markup=False, highlight=False, soft_wrap=True)


class Failed(Exception):
    """A failure the user can act on. avp prints the message, without a
    traceback, and exits 1."""

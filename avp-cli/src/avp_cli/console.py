"""How avp prints: results to stdout, progress and errors to stderr."""

import logging
from typing import Annotated

import typer
from rich.console import Console

out = Console()
err = Console(stderr=True)

verbose: bool = False
"""Set by a command's --verbose, through `set_verbose`."""

VerboseOption = Annotated[
    bool, typer.Option("--verbose", help="Print more about what avp does, to stderr.")
]


def set_verbose(on: bool) -> None:
    """With --verbose, the OpenSandbox SDK's logs print as details too."""
    global verbose
    verbose = on
    sdk = logging.getLogger("opensandbox")
    for handler in sdk.handlers:
        if isinstance(handler, _Detail):
            sdk.removeHandler(handler)
    if on:
        sdk.addHandler(_Detail())
        sdk.setLevel(logging.INFO)


class _Detail(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # SandboxSync.create logs the create its adapter then logs and sends.
        if record.name == "opensandbox.sync.sandbox" and record.getMessage().startswith(
            "Creating sandbox"
        ):
            return
        detail(f"opensandbox: {record.getMessage()}")


def detail(text: str) -> None:
    """Print a line to stderr with --verbose only. Never a secret's value."""
    if verbose:
        err.print(text, style="dim", markup=False, highlight=False, soft_wrap=True)


class Failed(Exception):
    """A failure the user can act on. avp prints the message, without a
    traceback, and exits 1."""

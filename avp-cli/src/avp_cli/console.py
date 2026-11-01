"""How avp prints: results to stdout, progress and errors to stderr."""

from rich.console import Console

out = Console()
err = Console(stderr=True)


class Failed(Exception):
    """A failure the user can act on. avp prints the message, without a
    traceback, and exits 1."""

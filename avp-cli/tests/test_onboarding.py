"""The welcome screen must track the real command surface.

The `avp` (no-args) welcome screen in onboarding.py is curated by hand:
grouped sections, narrative descriptions. The risk is drift: a subcommand
gets registered in `_build_parser()` and never added to the screen. This
test walks the actual argparse tree and asserts every command path
appears in the rendered welcome text, so adding a command without
documenting it fails CI instead of shipping silently.
"""

from __future__ import annotations

import argparse
from io import StringIO

from rich.console import Console

from avp_cli.cli import _build_parser
from avp_cli.onboarding import welcome

# Command paths intentionally left off the welcome screen. Empty today;
# add a path here (with a reason) rather than weakening the test.
_UNDOCUMENTED: set[str] = set()


def _command_paths(parser: argparse.ArgumentParser, prefix: str) -> list[str]:
    """Every `avp <group> [<sub> ...]` path the parser accepts, recursively."""
    paths: list[str] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                path = f"{prefix} {name}"
                paths.append(path)
                paths.extend(_command_paths(sub, path))
    return paths


def _rendered_welcome() -> str:
    out = Console(file=StringIO(), width=300, force_terminal=False)
    out.print(welcome())
    return out.file.getvalue()


def test_welcome_lists_every_registered_command():
    text = _rendered_welcome()
    missing = [
        path
        for path in _command_paths(_build_parser(), "avp")
        if path not in _UNDOCUMENTED and path not in text
    ]
    assert not missing, (
        f"commands registered in the parser but absent from the welcome screen: {missing}. "
        "Add them to the relevant section in onboarding.py (or to _UNDOCUMENTED with a reason)."
    )

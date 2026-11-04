"""How avp asks the user something before going ahead."""

import sys

import questionary

from avp_cli.console import Failed


def interactive() -> bool:
    """Whether there is a terminal to ask on."""
    return sys.stdin.isatty()


def confirm(question: str, yes: bool) -> bool:
    """Whether to go ahead: True with `yes`, else the user's answer, No by
    default. Without a terminal to ask on, fails with the hint to give
    --yes."""
    if yes:
        return True
    if not interactive():
        raise Failed(f"{question} There is no terminal to ask on; give --yes to go ahead.")
    return bool(questionary.confirm(question, default=False).ask())

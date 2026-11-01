"""The command tree matches COMMANDS.md."""

import pytest
from typer.testing import CliRunner

from avp_cli.cli import app

COMMANDS = [
    ["run"],
    ["eval", "run"],
    ["eval", "list"],
    ["eval", "show"],
    ["eval", "delete"],
    ["conformance", "check"],
    ["conformance", "list"],
    ["agent", "create"],
    ["agent", "list"],
    ["agent", "describe"],
    ["agent", "rebuild"],
    ["agent", "delete"],
    ["agent", "exec"],
    ["commission", "new"],
    ["commission", "check"],
    ["secret", "set"],
    ["secret", "login"],
    ["secret", "list"],
    ["secret", "delete"],
    ["sandbox", "start"],
    ["sandbox", "stop"],
    ["sandbox", "status"],
]


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_command_has_help(command: list[str]) -> None:
    result = CliRunner().invoke(app, [*command, "--help"])
    assert result.exit_code == 0, result.output

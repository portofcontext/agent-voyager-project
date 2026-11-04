"""The `avp` command tree, as COMMANDS.md describes it. Commands not built yet
raise NotImplementedError."""

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from avp_cli import console
from avp_cli._cli_common import AgentOption
from avp_cli.agents import cli as agent_cli
from avp_cli.conformance import cli as conformance_cli
from avp_cli.eval import cli as eval_cli
from avp_cli.runs import cli as run_cli
from avp_cli.sandbox import cli as sandbox_cli
from avp_cli.vault import cli as vault_cli

app = typer.Typer(no_args_is_help=True, help="Run, evaluate, and check AVP agents in sandboxes.")
commission_app = typer.Typer(no_args_is_help=True, help="Commission files.")

app.command()(run_cli.run)
app.add_typer(eval_cli.app, name="eval")
app.add_typer(conformance_cli.app, name="conformance")
app.add_typer(agent_cli.app, name="agent")
app.add_typer(commission_app, name="commission")
app.add_typer(vault_cli.app, name="vault")
app.add_typer(sandbox_cli.app, name="sandbox")


@commission_app.command("new")
def commission_new(
    agent: AgentOption,
    model: Annotated[str, typer.Option(help="The model, as provider/model.")],
    prompt: Annotated[str | None, typer.Option(help="The task.")] = None,
) -> None:
    """Write a Commission for an agent, with its built-in items listed."""
    raise NotImplementedError


@commission_app.command("check")
def commission_check(
    path: Annotated[Path, typer.Argument(help="The Commission file.")],
    agent: Annotated[str | None, typer.Option(help="Also apply the checks for this agent.")] = None,
) -> None:
    """Validate a Commission and apply the Commission checks for an agent."""
    raise NotImplementedError


def main() -> None:
    # The OpenSandbox SDK logs retries that then succeed, and failures that avp
    # reports itself.
    sdk = logging.getLogger("opensandbox")
    sdk.addHandler(logging.NullHandler())
    sdk.propagate = False
    try:
        app()
    except console.Failed as failure:
        console.err.print(f"[red]error:[/red] {escape(str(failure))}", highlight=False)
        if cause := failure.__cause__ or failure.__context__:
            console.detail(f"Caused by {type(cause).__name__}: {cause}")
        raise SystemExit(1) from None

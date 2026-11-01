"""The `avp` command tree, as COMMANDS.md describes it. Commands not built yet
raise NotImplementedError."""

from pathlib import Path
from typing import Annotated

import typer

from avp_cli.agents import cli as agent_cli
from avp_cli.console import Failed, err
from avp_cli.runs import cli as run_cli
from avp_cli.sandbox import cli as sandbox_cli

app = typer.Typer(no_args_is_help=True, help="Run, evaluate, and check AVP agents in sandboxes.")
eval_app = typer.Typer(
    no_args_is_help=True,
    help="Run datasets against agents and Commissions, and score the results.",
)
conformance_app = typer.Typer(
    no_args_is_help=True, help="Check that an agent follows the spec's rules for agents."
)
commission_app = typer.Typer(no_args_is_help=True, help="Commission files.")
secret_app = typer.Typer(
    no_args_is_help=True, help="Credentials written to each sandbox's Credential Vault."
)

app.command()(run_cli.run)
app.add_typer(eval_app, name="eval")
app.add_typer(conformance_app, name="conformance")
app.add_typer(agent_cli.app, name="agent")
app.add_typer(commission_app, name="commission")
app.add_typer(secret_app, name="secret")
app.add_typer(sandbox_cli.app, name="sandbox")

AgentOption = Annotated[str, typer.Option("--agent", help="An installed agent.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print JSON.")]


@eval_app.command("run")
def eval_run(
    path: Annotated[Path, typer.Argument(help="The eval file.")],
    agent: Annotated[list[str] | None, typer.Option(help="Run only these agents.")] = None,
    model: Annotated[str | None, typer.Option(help="Use this model for every Commission.")] = None,
    max_items: Annotated[int | None, typer.Option(help="Run at most this many items.")] = None,
    threshold: Annotated[float | None, typer.Option(help="Fail below this mean score.")] = None,
    resume: Annotated[str | None, typer.Option(help="Finish this earlier run.")] = None,
    json: JsonOption = False,
) -> None:
    """Run an eval file and print the scoreboard."""
    raise NotImplementedError


@eval_app.command("list")
def eval_list(limit: Annotated[int, typer.Option(help="Show this many runs.")] = 20) -> None:
    """List past eval runs."""
    raise NotImplementedError


@eval_app.command("show")
def eval_show(
    run_id: Annotated[str | None, typer.Argument(help="The run; the latest when omitted.")] = None,
    agent: Annotated[str | None, typer.Option(help="Show only this agent.")] = None,
    json: JsonOption = False,
) -> None:
    """Show one run's scoreboard and per-item results."""
    raise NotImplementedError


@eval_app.command("delete")
def eval_delete(
    run_id: Annotated[str | None, typer.Argument(help="The run to delete.")] = None,
    all: Annotated[bool, typer.Option("--all", help="Delete every run.")] = False,
) -> None:
    """Delete past runs and their trajectories."""
    raise NotImplementedError


@conformance_app.command("check")
def conformance_check(
    agent: AgentOption,
    model: Annotated[str | None, typer.Option(help="Run the cases with this model.")] = None,
    rule: Annotated[
        list[str] | None, typer.Option(help="Run only the cases for this rule.")
    ] = None,
    case: Annotated[list[str] | None, typer.Option(help="Run only this case.")] = None,
    keep_trajectories: Annotated[
        Path | None, typer.Option(help="Save each case's Trajectory in this directory.")
    ] = None,
    json: JsonOption = False,
) -> None:
    """Run the cases against an agent and report pass, fail, or skip by rule."""
    raise NotImplementedError


@conformance_app.command("list")
def conformance_list(
    rule: Annotated[
        list[str] | None, typer.Option(help="List only the cases for this rule.")
    ] = None,
) -> None:
    """List the cases and the rule each one covers."""
    raise NotImplementedError


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


@secret_app.command("set")
def secret_set(
    name: Annotated[str, typer.Argument(help="The name a Commission refers to.")],
    value: Annotated[str | None, typer.Argument(help="The value; prompted when omitted.")] = None,
) -> None:
    """Store a secret under a name a Commission can refer to."""
    raise NotImplementedError


@secret_app.command("login")
def secret_login(
    name: Annotated[str, typer.Argument(help="The name a Commission refers to.")],
    url: Annotated[str, typer.Option(help="The MCP server's URL.")],
    scope: Annotated[list[str] | None, typer.Option(help="An OAuth scope to request.")] = None,
) -> None:
    """Sign in to an MCP server with OAuth and store the token."""
    raise NotImplementedError


@secret_app.command("list")
def secret_list() -> None:
    """List secret names and where each comes from."""
    raise NotImplementedError


@secret_app.command("delete")
def secret_delete(name: Annotated[str, typer.Argument(help="The secret.")]) -> None:
    """Delete a secret."""
    raise NotImplementedError


def main() -> None:
    try:
        app()
    except Failed as failure:
        err.print(f"[red]error:[/red] {failure}", highlight=False)
        raise SystemExit(1) from None

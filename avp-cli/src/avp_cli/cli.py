"""The `avp` command tree, as COMMANDS.md describes it. Commands not built yet
raise NotImplementedError."""

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True, help="Run, evaluate, and check AVP agents in sandboxes.")
eval_app = typer.Typer(
    no_args_is_help=True,
    help="Run datasets against agents and Commissions, and score the results.",
)
conformance_app = typer.Typer(
    no_args_is_help=True, help="Check that an agent follows the spec's rules for agents."
)
agent_app = typer.Typer(
    no_args_is_help=True, help="Agents: an AVP agent release plus the environment it runs in."
)
commission_app = typer.Typer(no_args_is_help=True, help="Commission files.")
secret_app = typer.Typer(
    no_args_is_help=True, help="Credentials written to each sandbox's Credential Vault."
)
sandbox_app = typer.Typer(no_args_is_help=True, help="The OpenSandbox service every agent runs on.")

app.add_typer(eval_app, name="eval")
app.add_typer(conformance_app, name="conformance")
app.add_typer(agent_app, name="agent")
app.add_typer(commission_app, name="commission")
app.add_typer(secret_app, name="secret")
app.add_typer(sandbox_app, name="sandbox")

AgentOption = Annotated[
    str,
    typer.Option(
        "--agent",
        help="Your agent (pi-py), or a release (avp-pi, avp-pi@0.4.1) in a default environment.",
    ),
]
JsonOption = Annotated[bool, typer.Option("--json", help="Print JSON.")]


@app.command()
def run(
    commission: Annotated[Path, typer.Option(help="The Commission file.")],
    agent: AgentOption,
    out: Annotated[Path | None, typer.Option(help="Where to write the Trajectory.")] = None,
    timeout: Annotated[
        str | None, typer.Option(help="Stop the run after this long, e.g. 30m.")
    ] = None,
) -> None:
    """Run one agent on one Commission and write its Trajectory."""
    raise NotImplementedError


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


@agent_app.command("create")
def agent_create(
    name: Annotated[str, typer.Argument(help="The new agent's name.")],
    from_: Annotated[
        str,
        typer.Option(
            "--from", help="A release (avp-pi, avp-pi@0.4.1) or a working copy's directory."
        ),
    ],
    image: Annotated[str | None, typer.Option(help="The base image.")] = None,
    apt: Annotated[list[str] | None, typer.Option(help="An apt package to install.")] = None,
    pip: Annotated[list[str] | None, typer.Option(help="A pip package to install.")] = None,
    file: Annotated[list[str] | None, typer.Option(help="Copy a file in: HOST:SANDBOX.")] = None,
    setup: Annotated[list[str] | None, typer.Option(help="A command to run in the image.")] = None,
    allow_host: Annotated[
        list[str] | None, typer.Option(help="A host the agent may reach.")
    ] = None,
    cpu: Annotated[float | None, typer.Option(help="CPUs for each sandbox.")] = None,
    memory: Annotated[str | None, typer.Option(help="Memory for each sandbox, e.g. 4g.")] = None,
    like: Annotated[str | None, typer.Option(help="Copy another agent's environment.")] = None,
) -> None:
    """Define an agent and build its sandbox image."""
    raise NotImplementedError


@agent_app.command("list")
def agent_list(
    available: Annotated[
        bool, typer.Option(help="List the AVP releases you can create from instead.")
    ] = False,
) -> None:
    """List your agents with their release, version, and image status."""
    raise NotImplementedError


@agent_app.command("ping")
def agent_ping(name: Annotated[str, typer.Argument(help="The agent.")]) -> None:
    """Check that the agent starts in its sandbox, without loading it."""
    raise NotImplementedError


@agent_app.command("describe")
def agent_describe(
    name: Annotated[str, typer.Argument(help="The agent.")],
    json: JsonOption = False,
) -> None:
    """Show the agent's Agent Descriptor, as its describe command returns it."""
    raise NotImplementedError


@agent_app.command("rebuild")
def agent_rebuild(name: Annotated[str, typer.Argument(help="The agent.")]) -> None:
    """Rebuild an agent's image after a release or working-copy change."""
    raise NotImplementedError


@agent_app.command("delete")
def agent_delete(name: Annotated[str, typer.Argument(help="The agent.")]) -> None:
    """Delete an agent and its image."""
    raise NotImplementedError


@agent_app.command("exec")
def agent_exec(
    name: Annotated[str, typer.Argument(help="The agent.")],
    command: Annotated[list[str], typer.Argument(help="The command, after --.")],
) -> None:
    """Run a command in a fresh sandbox of the agent, without the agent."""
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


@sandbox_app.command("start")
def sandbox_start() -> None:
    """Start the service. Agent commands also start it when needed."""
    raise NotImplementedError


@sandbox_app.command("stop")
def sandbox_stop() -> None:
    """Stop the service and any sandboxes still running."""
    raise NotImplementedError


@sandbox_app.command("status")
def sandbox_status() -> None:
    """Show whether the service is running, where, and whether the engine is reachable."""
    raise NotImplementedError

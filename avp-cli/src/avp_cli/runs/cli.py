"""`avp run`: one agent on one Commission."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from avp.commission import Commission
from avp.trajectory import AgentStoppedEvent, ErrorOccurredEvent, parse_trajectory_event
from avp_cli.agents import command, store
from avp_cli.console import Failed, err, out
from avp_cli.engine import images
from avp_cli.runs import directory, environment, network, volumes
from avp_cli.sandbox import sandboxes

STDERR_LINES = 5


def run(
    commission: Annotated[Path, typer.Option(help="The Commission file.")],
    agent: Annotated[str, typer.Option(help="An installed agent.")],
    env: Annotated[
        list[str] | None,
        typer.Option(help="NAME=VALUE for the agent's environment, or NAME to copy it from yours."),
    ] = None,
    env_file: Annotated[
        list[Path] | None,
        typer.Option(help="A file of NAME=VALUE lines for the agent's environment."),
    ] = None,
    allow_host: Annotated[
        list[str] | None,
        typer.Option(
            help="Another host the agent may reach, besides the model's and the HTTP MCP"
            " servers': a domain, *.domain, IP address, or CIDR range."
        ),
    ] = None,
    volume: Annotated[
        list[str] | None,
        typer.Option(
            "--volume",
            "-v",
            help="HOST:SANDBOX to mount a host path in the sandbox, or HOST:SANDBOX:ro read-only.",
        ),
    ] = None,
) -> None:
    """Run one agent on one Commission and write its Trajectory. The agent's
    environment has only the variables given with --env and --env-file. It can
    reach only the model's host, the Commission's HTTP MCP servers, and the hosts
    given with --allow-host."""
    text = commission.read_text()
    try:
        parsed = Commission.model_validate_json(text)
    except ValidationError as exc:
        raise Failed(f"{commission} isn't a valid Commission: {exc}") from None
    variables = environment.variables(env or [], env_file or [])
    environment.check(parsed, variables)
    hosts = network.allowed_hosts(parsed, allow_host or [])
    mounts = volumes.parse(volume or [])
    installed = store.load(agent)
    run_directory = directory.create(parsed.run_id, text)
    trajectory = run_directory / directory.TRAJECTORY
    if not any(network.MODEL in reasons for reasons in hosts.values()):
        err.print(
            f"warning: avp knows no host for {parsed.model.provider!r} models; set"
            " model.base_url, or allow its host with --allow-host",
            highlight=False,
        )
    # err.print(f"Allowed hosts: {network.describe(hosts)}", highlight=False)
    if mounts:
        err.print(f"Volumes: {volumes.describe(mounts)}", highlight=False)
    with sandboxes.sandbox(installed.image, run_directory, list(hosts), mounts) as box:
        result = command.run(
            box,
            images.entrypoint(installed.image),
            f"{sandboxes.IO}/{directory.COMMISSION}",
            f"{sandboxes.IO}/{directory.TRAJECTORY}",
            variables,
        )
    if result.stderr:
        (run_directory / directory.STDERR).write_text(result.stderr)
    # Shown even when the agent crashed, since its events up to then are there.
    if trajectory.is_file():
        report(trajectory)
        out.print(f"Trajectory: {trajectory}", highlight=False)
    if result.exit_code != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-STDERR_LINES:])
        raise Failed(
            f"the agent exited with {result.exit_code}"
            + (
                f". Its stderr ends:\n{tail}\nAll of it: {run_directory / directory.STDERR}"
                if tail
                else ""
            )
        )


def report(trajectory: Path) -> None:
    """Each event's type, with the details of errors and the stop."""
    for line in trajectory.read_text().splitlines():
        event = parse_trajectory_event(line)
        if event is None:
            continue
        if isinstance(event, ErrorOccurredEvent):
            err.print(
                f"{event.type}: {event.data.error_code}: {event.data.error_message}",
                highlight=False,
            )
        elif isinstance(event, AgentStoppedEvent):
            err.print(f"{event.type}: {event.data.reason}", highlight=False)
        else:
            err.print(event.type, style="dim")

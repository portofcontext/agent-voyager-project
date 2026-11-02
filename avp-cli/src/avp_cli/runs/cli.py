"""`avp run`: one agent on one Commission."""

import shlex
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from avp.commission import Commission
from avp_cli import console
from avp_cli.agents import command, store
from avp_cli.console import Failed, VerboseOption, detail, err, line, out
from avp_cli.engine import images
from avp_cli.runs import credentials, directory, environment, events, network, volumes
from avp_cli.sandbox import sandboxes

STDERR_LINES = 5
POLL_S = 0.1
"""How often avp looks for new events."""


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
    verbose: VerboseOption = False,
) -> None:
    """Run one agent on one Commission and write its Trajectory. The agent's
    environment has only the variables given with --env and --env-file. It can
    reach only the model's host, the Commission's HTTP MCP servers, and the hosts
    given with --allow-host. A {"proxy": NAME} credential comes from `avp vault`,
    and the sandbox's Credential Vault adds it to the agent's requests."""
    console.set_verbose(verbose)
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
    entrypoint = images.entrypoint(installed.image)
    detail(f"Image: {installed.image}, entrypoint {shlex.join(entrypoint)}")
    vault = credentials.vault(parsed)
    run_directory = directory.create(parsed.run_id, text)
    detail(f"Run directory: {run_directory}")
    trajectory = run_directory / directory.TRAJECTORY
    if not any(network.MODEL in reasons for reasons in hosts.values()):
        detail(
            f"Warning: avp knows no host for {parsed.model.provider!r} models; set"
            " model.base_url, or allow its host with --allow-host"
        )
    detail(f"Allowed hosts: {network.describe(hosts)}")
    if mounts:
        detail(f"Volumes: {volumes.describe(mounts)}")
    with (
        err.status(line("Starting a sandbox for ", (agent, "bold"))) as status,
        sandboxes.sandbox(installed.image, run_directory, list(hosts), mounts, vault) as box,
    ):
        follower = events.Follower(trajectory)
        result = _following(
            follower,
            lambda: command.run(
                box,
                entrypoint,
                f"{sandboxes.IO}/{directory.COMMISSION}",
                f"{sandboxes.IO}/{directory.TRAJECTORY}",
                variables,
            ),
            lambda seconds: status.update(
                line("Running ", (agent, "bold"), " - ", (events.elapsed(seconds), "dim"))
            ),
        )
    follower.finish()
    if result.stderr:
        (run_directory / directory.STDERR).write_text(result.stderr)
    # Shown even when the agent crashed, since its events up to then are there.
    if trajectory.is_file():
        out.print(f"\nTrajectory: {trajectory}", highlight=False, soft_wrap=True)
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


def _following(
    follower: events.Follower,
    run: Callable[[], sandboxes.Result],
    tick: Callable[[float], None],
) -> sandboxes.Result:
    """Run the agent in a thread and print its events as they arrive, calling
    `tick` with the seconds it has run each time avp looks. On
    Ctrl-C, the sandbox is deleted, which ends the agent's command; the thread
    is a daemon, so it doesn't hold avp open."""
    outcome: list[sandboxes.Result | BaseException] = []

    def target() -> None:
        try:
            outcome.append(run())
        except BaseException as error:
            outcome.append(error)

    thread = threading.Thread(target=target, daemon=True)
    began = time.monotonic()
    thread.start()
    while thread.is_alive():
        follower.poll()
        tick(time.monotonic() - began)
        thread.join(POLL_S)
    if isinstance(outcome[0], BaseException):
        raise outcome[0]
    return outcome[0]

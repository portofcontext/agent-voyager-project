"""Dispatching a Commission to an agent in a sandbox, and waiting for it:
what `avp run` does, and what an eval does for each of its runs."""

import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from opensandbox.models.sandboxes import Volume

from avp.commission import Commission
from avp_cli import paths
from avp_cli.agents import command, store
from avp_cli.console import detail
from avp_cli.runs import credentials, directory, environment, network, volumes
from avp_cli.sandbox import sandboxes

Watch = Callable[[Path, Callable[[], sandboxes.Result]], sandboxes.Result]
"""Wraps the agent's command while it runs: called with the Trajectory's path
and the command, it runs the command and returns its result. `avp run` prints
the events as they arrive."""


@dataclass(frozen=True)
class Options:
    """How a run is set up, besides its Commission."""

    env: dict[str, str] = field(default_factory=dict)
    """The agent's whole environment, besides what the image sets."""
    allow_hosts: list[str] = field(default_factory=list)
    """Hosts the agent may reach, besides the model's and the Commission's
    HTTP MCP servers'."""
    volumes: list[Volume] = field(default_factory=list)
    """Host paths mounted in the sandbox."""
    directory: Path | None = None
    """The run's directory, which must not exist yet. Default:
    `~/.avp/runs/<time>-<run_id>/`."""


@dataclass(frozen=True)
class Finished:
    directory: Path
    """Holds the Commission, the Trajectory, and the agent's stderr."""
    exit_code: int | None
    stderr: str

    @property
    def trajectory(self) -> Path:
        return self.directory / paths.TRAJECTORY


def dispatch(
    agent: store.Agent,
    entrypoint: list[str],
    commission: Commission,
    options: Options | None = None,
    text: str | None = None,
    watch: Watch | None = None,
) -> Finished:
    """Sends the Commission to the agent and waits for it. `text` is the
    Commission as given, kept in the run's directory; by default its JSON.
    Raises Failed before the agent starts, for a variable or secret the
    Commission needs or a sandbox that won't start. Once the agent is running,
    how it ended is the exit code."""
    options = options or Options()
    environment.check(commission, options.env)
    hosts = network.allowed_hosts(commission, options.allow_hosts)
    vault = credentials.vault(commission)
    detail(f"Image: {agent.image}, entrypoint {shlex.join(entrypoint)}")
    if text is None:
        text = commission.model_dump_json(exclude_none=True)
    run_directory = directory.create(commission.run_id, text, options.directory)
    detail(f"Run directory: {run_directory}")
    if not any(network.MODEL in reasons for reasons in hosts.values()):
        detail(
            f"Warning: avp knows no host for {commission.model.provider!r} models; set"
            " model.base_url, or allow its host"
        )
    detail(f"Allowed hosts: {network.describe(hosts)}")
    if options.volumes:
        detail(f"Volumes: {volumes.describe(options.volumes)}")
    with sandboxes.sandbox(agent.image, run_directory, list(hosts), options.volumes, vault) as box:

        def agent_command() -> sandboxes.Result:
            return command.run(
                box,
                entrypoint,
                f"{sandboxes.IO}/{paths.COMMISSION}",
                f"{sandboxes.IO}/{paths.TRAJECTORY}",
                options.env,
            )

        trajectory = run_directory / paths.TRAJECTORY
        result = watch(trajectory, agent_command) if watch else agent_command()
    if result.stderr:
        (run_directory / paths.STDERR).write_text(result.stderr)
    return Finished(run_directory, result.exit_code, result.stderr)

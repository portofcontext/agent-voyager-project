"""`avp agent`: install agents and check them in their sandboxes."""

import shlex
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table
from rich.text import Text

from avp_cli import console, paths
from avp_cli._cli_common import VerboseOption
from avp_cli.agents import builtins, command, store
from avp_cli.console import Failed, detail, err, line, out
from avp_cli.engine import images
from avp_cli.sandbox import sandboxes

app = typer.Typer(
    no_args_is_help=True,
    help="Agents: an image whose ENTRYPOINT is an AVP agent command line.",
)
NameArgument = Annotated[str, typer.Argument(help="The agent.")]


@app.command()
def install(
    name: Annotated[str, typer.Argument(help="A name for the agent.")],
    dockerfile: Annotated[
        Path | None, typer.Argument(help="A custom agent's Dockerfile. Omit for a built-in agent.")
    ] = None,
    context: Annotated[
        Path | None,
        typer.Option(help="The build context (default: the Dockerfile's directory)."),
    ] = None,
    verbose: VerboseOption = False,
) -> None:
    """Build the agent's image, check it answers `ping` and `describe` in a
    sandbox, and save it. Installing over an agent replaces it. --verbose
    prints the build's output."""
    console.set_verbose(verbose)
    store.check_name(name)
    builtin = None
    if dockerfile is None:
        builtin = builtins.get(name)
        if context is not None:
            raise Failed("--context requires a custom Dockerfile")
    elif name in builtins.catalog().agents:
        raise Failed(f"{name!r} is a built-in name; choose another name for a custom Dockerfile")
    building = ("Building ", (name, "bold"), " image")
    began = time.monotonic()
    with err.status(line(*building)) as status:

        def show(*parts: str | tuple[str, str]) -> None:
            status.update(line(*parts))

        def step(step: images.Step) -> None:
            cached = (" (cached)", "dim") if step.cached else ""
            show(*building, f" - step {step.number}: ", (step.instruction, "dim"), cached)

        source = (
            builtins.context(name)
            if dockerfile is None
            else nullcontext(context or dockerfile.parent)
        )
        with source as directory:
            image = images.build(
                dockerfile or directory / "Dockerfile",
                directory,
                tag=f"localhost/avp/{name}",
                step=step,
            )
        built = time.monotonic() - began
        entrypoint = _entrypoint(image)
        show("Starting a sandbox for ", (name, "bold"))
        with sandboxes.sandbox(image) as box:
            show("Checking ", ("ping", "bold"))
            version = command.ping(box, entrypoint)
            show("Checking ", ("describe", "bold"))
            descriptor = command.describe(box, entrypoint)
            if builtin and (descriptor.agent_name, descriptor.agent_version) != (
                builtin.agent_name,
                builtin.version,
            ):
                raise Failed(
                    f"expected {builtin.agent_name} {builtin.version}; the image describes "
                    f"{descriptor.agent_name} {descriptor.agent_version}"
                )
    store.save(store.Agent(name=name, image=image))
    err.print(
        Text.assemble(
            "Installed ",
            (name, "bold"),
            ": ",
            (descriptor.agent_name, "bold"),
            f" {descriptor.agent_version}, AVP {version}, ",
            (f"in {image} (built in {built:.0f}s)", "dim"),
        )
    )


@app.command()
def uninstall(name: NameArgument, verbose: VerboseOption = False) -> None:
    """Remove an agent and its image."""
    console.set_verbose(verbose)
    agent = store.load(name)
    images.remove(agent.image)
    detail(f"Removed {agent.image}")
    store.delete(name)
    err.print(Text.assemble("Uninstalled ", (name, "bold")))


@app.command("list")
def list_(
    builtin: Annotated[bool, typer.Option("--builtin", help="List the built-in agents.")] = False,
    verbose: VerboseOption = False,
) -> None:
    """List installed agents, or the built-in agents available to install."""
    console.set_verbose(verbose)
    if builtin:
        table = Table("Name", "Agent", "Version", box=None)
        for name, entry in builtins.catalog().agents.items():
            table.add_row(Text(name, "bold"), entry.agent_name, entry.version)
        out.print(table)
        return
    detail(f"Agents: {paths.agents()}")
    table = Table("Name", "Image", box=None)
    for agent in store.installed():
        table.add_row(Text(agent.name, "bold"), agent.image)
    out.print(table)


@app.command()
def ping(name: NameArgument, verbose: VerboseOption = False) -> None:
    """Check that the agent starts in a sandbox, without loading it."""
    console.set_verbose(verbose)
    agent = store.load(name)
    entrypoint = _entrypoint(agent.image)
    with sandboxes.sandbox(agent.image) as box:
        version = command.ping(box, entrypoint)
    out.print(f"pong (AVP {version})")


@app.command()
def describe(name: NameArgument, verbose: VerboseOption = False) -> None:
    """Print the agent's Agent Descriptor, from its `describe` in a sandbox."""
    console.set_verbose(verbose)
    agent = store.load(name)
    entrypoint = _entrypoint(agent.image)
    descriptor = command.describe_in_sandbox(agent, entrypoint)
    out.print_json(descriptor.model_dump_json(exclude_none=True))


def _entrypoint(image: str) -> list[str]:
    entrypoint = images.entrypoint(image)
    detail(f"Image: {image}, entrypoint {shlex.join(entrypoint)}")
    return entrypoint

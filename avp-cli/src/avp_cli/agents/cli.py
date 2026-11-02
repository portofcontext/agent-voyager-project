"""`avp agent`: install agents and check them in their sandboxes."""

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from avp_cli.agents import command, store
from avp_cli.console import err, out
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
        Path, typer.Argument(help="A Dockerfile whose ENTRYPOINT is the agent's command line.")
    ],
    context: Annotated[
        Path | None,
        typer.Option(help="The build context (default: the Dockerfile's directory)."),
    ] = None,
) -> None:
    """Build the agent's image, check it answers `ping` and `describe` in a
    sandbox, and save it. Installing over an agent replaces it."""
    store.check_name(name)
    image = images.build(dockerfile, context or dockerfile.parent, tag=f"localhost/avp/{name}")
    entrypoint = images.entrypoint(image)
    with sandboxes.sandbox(image) as box:
        version = command.ping(box, entrypoint)
        descriptor = command.describe(box, entrypoint)
    store.save(store.Agent(name=name, image=image))
    err.print(
        f"Installed {name}: {descriptor.agent_name} {descriptor.agent_version}, "
        f"AVP {version}, in {image}"
    )


@app.command()
def uninstall(name: NameArgument) -> None:
    """Remove an agent and its image."""
    agent = store.load(name)
    images.remove(agent.image)
    store.delete(name)
    err.print(f"Uninstalled {name}")


@app.command("list")
def list_() -> None:
    """List your agents."""
    table = Table("Name", "Image", box=None)
    for agent in store.installed():
        table.add_row(agent.name, agent.image)
    out.print(table)


@app.command()
def ping(name: NameArgument) -> None:
    """Check that the agent starts in a sandbox, without loading it."""
    agent = store.load(name)
    with sandboxes.sandbox(agent.image) as box:
        version = command.ping(box, images.entrypoint(agent.image))
    out.print(f"pong (AVP {version})")


@app.command()
def describe(name: NameArgument) -> None:
    """Print the agent's Agent Descriptor, from its `describe` in a sandbox."""
    agent = store.load(name)
    with sandboxes.sandbox(agent.image) as box:
        descriptor = command.describe(box, images.entrypoint(agent.image))
    out.print_json(descriptor.model_dump_json(exclude_none=True))

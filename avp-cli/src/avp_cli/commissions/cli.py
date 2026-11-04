"""Create, check, and keep reusable Commissions."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue

from avp.commission import AgentSettings
from avp_cli._cli_common import AgentOption, YesOption
from avp_cli.agents import command
from avp_cli.agents import store as agents
from avp_cli.commissions import store
from avp_cli.commissions.check import builtins, check, require_valid
from avp_cli.console import Failed, err, out
from avp_cli.engine import images
from avp_cli.prompts import confirm

app = typer.Typer(no_args_is_help=True, help="Create, check, and save reusable Commissions.")


@app.command("new")
def new(
    agent: AgentOption,
    model: Annotated[str, typer.Option(help="The model, as provider/model.")],
    prompt: Annotated[str, typer.Option(help="The task.")] = "",
) -> None:
    """Print JSON with the agent's version and built-in items. Redirect it to a file."""
    provider, separator, model_id = model.partition("/")
    if not separator or not provider or not model_id:
        raise Failed("--model must be provider/model")
    installed = agents.load(agent)
    descriptor = command.describe_in_sandbox(installed, images.entrypoint(installed.image))
    value: dict[str, JsonValue] = {
        "avp_version": "0.1",
        "model": {"provider": provider, "id": model_id},
        "prompt": prompt,
        "agents": {
            descriptor.agent_name: AgentSettings.model_validate(
                {
                    "version": descriptor.agent_version,
                    **builtins(descriptor),
                }
            ).model_dump(mode="json", exclude_none=True)
        },
    }
    require_valid(check(value, descriptor))
    out.print_json(data=value)


@app.command("check")
def check_file(
    source: Annotated[str, typer.Argument(help="A file path or saved Commission name.")],
    agent: Annotated[str | None, typer.Option(help="Also check this agent's Descriptor.")] = None,
) -> None:
    """Report every problem. Errors exit 1; warnings alone exit 0."""
    value = store.read(store.resolve(source))
    descriptor = None
    if agent is not None:
        installed = agents.load(agent)
        descriptor = command.describe_in_sandbox(installed, images.entrypoint(installed.image))
    problems = check(value, descriptor)
    for problem in problems:
        err.print(str(problem), markup=False, highlight=False)
    if any(p.level == "error" for p in problems):
        raise typer.Exit(1)
    err.print("Commission is valid")


@app.command("save")
def save(
    name: Annotated[str, typer.Argument(help="The name to save under.")],
    path: Annotated[Path, typer.Argument(help="The Commission file.")],
    force: Annotated[bool, typer.Option(help="Replace an existing saved Commission.")] = False,
) -> None:
    """Check and save a file, omitting per-run identity. Does not check an agent."""
    store.check_name(name)
    value = store.read(path)
    require_valid(check(value))
    saved = store.save(name, value, replace=force)
    err.print(f"Saved {name}: {saved}", markup=False, highlight=False)


@app.command("list")
def list_commissions() -> None:
    """List saved Commission names."""
    for name in store.names():
        out.print(name, markup=False, highlight=False)


@app.command("delete")
def delete(
    name: Annotated[str, typer.Argument(help="The saved Commission name.")],
    yes: YesOption = False,
) -> None:
    """Delete a saved Commission. Keeps its past runs."""
    store.check_name(name)
    store.resolve(name)
    if not confirm(f"Delete Commission {name!r}?", yes):
        raise typer.Exit(1)
    store.delete(name)
    err.print(f"Deleted {name}", markup=False, highlight=False)

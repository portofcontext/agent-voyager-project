"""`avp vault`: secrets in the system's credential store."""

from typing import Annotated

import typer
from rich.table import Table

from avp_cli.console import Failed, err, out
from avp_cli.vault import store

app = typer.Typer(
    no_args_is_help=True,
    help="Secrets in the system's credential store, for Commissions to refer to by name.",
)
NameArgument = Annotated[str, typer.Argument(help="The name a Commission refers to.")]


@app.command("set")
def set_(
    name: NameArgument,
    value: Annotated[
        str | None,
        typer.Argument(help="The value; prompted for, without echo, when omitted."),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option(
            "--description", "-d", help="What the secret is for; kept when omitted, cleared by ''."
        ),
    ] = None,
) -> None:
    """Store a secret under a name a Commission can refer to. Setting a secret again replaces it."""
    store.check_name(name)
    if value is None:
        value = typer.prompt(f"Value for {name}", hide_input=True)
    store.set_(name, value, description)
    err.print(f'Stored {name}. A Commission refers to it as {{"proxy": "{name}"}}')


@app.command()
def login(
    name: NameArgument,
    url: Annotated[str, typer.Option(help="The MCP server's URL.")],
    scope: Annotated[list[str] | None, typer.Option(help="An OAuth scope to request.")] = None,
) -> None:
    """Sign in to an MCP server with OAuth and store the token."""
    raise NotImplementedError


@app.command("list")
def list_(
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Read each secret to check it is still in the store. "
            "On macOS, the Keychain may ask to allow each read.",
        ),
    ] = False,
) -> None:
    """List secrets' names, descriptions, and when each was last set."""
    table = Table("Name", "Description", "Updated", box=None)
    if check:
        table.add_column("In store")
    missing = []
    for secret in store.secrets():
        row = [
            secret.name,
            secret.description or "",
            f"{secret.updated.astimezone():%Y-%m-%d %H:%M}",
        ]
        if check:
            stored = store.stored(secret.name)
            if not stored:
                missing.append(secret.name)
            row.append("[green]✓[/green]" if stored else "[red]✗[/red]")
        table.add_row(*row)
    out.print(table)
    if missing:
        raise Failed(f"not in the store: {', '.join(missing)}. Set them again, or delete them")


@app.command()
def delete(name: Annotated[str, typer.Argument(help="The secret.")]) -> None:
    """Delete a secret."""
    store.delete(name)
    err.print(f"Deleted {name}")

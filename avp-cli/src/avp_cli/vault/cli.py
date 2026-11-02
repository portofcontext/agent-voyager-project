"""`avp vault`: secrets in the system's credential store."""

from datetime import datetime
from typing import Annotated

import typer
from rich.table import Table

from avp_cli import console, paths
from avp_cli.console import Failed, VerboseOption, detail, err, out
from avp_cli.vault import oauth, store

app = typer.Typer(
    no_args_is_help=True,
    help="Secrets in the system's credential store, for Commissions to refer to by name.",
)
NameArgument = Annotated[str, typer.Argument(help="The name a Commission refers to.")]
DescriptionOption = Annotated[
    str | None,
    typer.Option(
        "--description", "-d", help="What the secret is for; kept when omitted, cleared by ''."
    ),
]


@app.command("set")
def set_(
    name: NameArgument,
    value: Annotated[
        str | None,
        typer.Argument(help="The value; prompted for, without echo, when omitted."),
    ] = None,
    description: DescriptionOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Store a secret under a name a Commission can refer to. Setting a secret again replaces it."""
    console.set_verbose(verbose)
    _where()
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
    description: DescriptionOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Sign in to an MCP server with OAuth in the browser, and store the access
    token, the refresh token, and when the access token expires. Signing in
    again replaces them."""
    console.set_verbose(verbose)
    _where()
    store.check_name(name)
    secret = oauth.login(name, url, scope or [], description)
    err.print(f"\nSigned in to {url} as {name}. {_expiry(secret)}")


@app.command()
def refresh(name: NameArgument, verbose: VerboseOption = False) -> None:
    """Get a new access token for an OAuth sign-in with its refresh token."""
    console.set_verbose(verbose)
    _where()
    secret = oauth.refresh(name)
    err.print(f"Refreshed {name}. {_expiry(secret)}")


def _where() -> None:
    detail(f"Credential store: {store.backend()}")
    detail(f"Names and descriptions: {paths.vault()}")


def _time(when: datetime) -> str:
    return f"{when.astimezone():%Y-%m-%d %H:%M}"


def _expiry(secret: store.Secret) -> str:
    expires_at = secret.oauth.expires_at if secret.oauth else None
    if not expires_at:
        return "The token doesn't say when it expires."
    return f"The token expires at {_time(expires_at)}."


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
    verbose: VerboseOption = False,
) -> None:
    """List secrets' names, descriptions, when each was last set, and when an
    OAuth sign-in's token expires. With --verbose, also where each sign-in's
    token comes from."""
    console.set_verbose(verbose)
    _where()
    table = Table("Name", "Description", "Updated", "Expires", box=None)
    if check:
        table.add_column("In store")
    missing = []
    for secret in store.secrets():
        row = [
            secret.name,
            secret.description or "",
            _time(secret.updated),
            _expires(secret),
        ]
        if check:
            stored = store.stored(secret.name)
            if not stored:
                missing.append(secret.name)
            row.append("[green]✓[/green]" if stored else "[red]✗[/red]")
        table.add_row(*row)
    out.print(table)
    for secret in store.secrets():
        if secret.oauth:
            detail(f"{secret.name}: signed in to {secret.oauth.url}")
            detail(f"{secret.name}: token endpoint {secret.oauth.token_endpoint}")
            detail(f"{secret.name}: scopes requested {' '.join(secret.oauth.scopes) or 'none'}")
    if missing:
        raise Failed(f"not in the store: {', '.join(missing)}. Set them again, or delete them")


def _expires(secret: store.Secret) -> str:
    expires_at = secret.oauth.expires_at if secret.oauth else None
    if not expires_at:
        return ""
    when = _time(expires_at)
    return f"[red]{when}[/red]" if oauth.expired(secret) else when


@app.command()
def delete(
    name: Annotated[str, typer.Argument(help="The secret.")], verbose: VerboseOption = False
) -> None:
    """Delete a secret."""
    console.set_verbose(verbose)
    _where()
    store.delete(name)
    err.print(f"Deleted {name}")

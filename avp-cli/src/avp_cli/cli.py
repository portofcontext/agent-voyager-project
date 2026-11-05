"""The `avp` command tree, as COMMANDS.md describes it. Commands not built yet
raise NotImplementedError."""

import logging

import typer
from rich.markup import escape

from avp_cli import console, hello
from avp_cli.agents import cli as agent_cli
from avp_cli.commissions import cli as commission_cli
from avp_cli.conformance import cli as conformance_cli
from avp_cli.eval import cli as eval_cli
from avp_cli.runs import cli as run_cli
from avp_cli.sandbox import cli as sandbox_cli
from avp_cli.vault import cli as vault_cli

app = typer.Typer(no_args_is_help=True, help="Run, evaluate, and check AVP agents in sandboxes.")

app.command()(run_cli.run)
app.command("hello-world")(hello.hello_world)
app.add_typer(eval_cli.app, name="eval")
app.add_typer(conformance_cli.app, name="conformance")
app.add_typer(agent_cli.app, name="agent")
app.add_typer(commission_cli.app, name="commission")
app.add_typer(vault_cli.app, name="vault")
app.add_typer(sandbox_cli.app, name="sandbox")


def main() -> None:
    # The OpenSandbox SDK logs retries that then succeed, and failures that avp
    # reports itself.
    sdk = logging.getLogger("opensandbox")
    sdk.addHandler(logging.NullHandler())
    sdk.propagate = False
    try:
        app()
    except console.Failed as failure:
        console.err.print(f"[red]error:[/red] {escape(str(failure))}", highlight=False)
        if cause := failure.__cause__ or failure.__context__:
            console.detail(f"Caused by {type(cause).__name__}: {cause}")
        raise SystemExit(1) from None

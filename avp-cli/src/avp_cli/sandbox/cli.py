"""`avp sandbox`: the OpenSandbox service every agent runs on."""

import typer

from avp_cli import engine
from avp_cli.console import Failed, out
from avp_cli.sandbox import service

app = typer.Typer(no_args_is_help=True, help="The OpenSandbox service every agent runs on.")


@app.command()
def start() -> None:
    """Start the service. Agent commands also start it when needed."""
    service.start()
    out.print(f"OpenSandbox is running at 127.0.0.1:{service.PORT}")


@app.command()
def stop() -> None:
    """Stop the service."""
    out.print("Stopped OpenSandbox" if service.stop() else "OpenSandbox wasn't running")


@app.command()
def status() -> None:
    """Show the container engine, and whether the service is running."""
    try:
        out.print(f"Engine: {engine.name()} at {engine.where()}", highlight=False)
    except Failed as failure:
        out.print(f"Engine: {failure}", highlight=False)
    if service.running():
        out.print(f"OpenSandbox: running at 127.0.0.1:{service.PORT}", highlight=False)
    else:
        out.print("OpenSandbox: not running")

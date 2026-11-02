"""`avp sandbox`: the OpenSandbox service every agent runs on."""

import typer

from avp_cli import console, engine, paths
from avp_cli.console import Failed, VerboseOption, detail, out
from avp_cli.sandbox import service

app = typer.Typer(no_args_is_help=True, help="The OpenSandbox service every agent runs on.")


@app.command()
def start(verbose: VerboseOption = False) -> None:
    """Start the service. Agent commands also start it when needed."""
    console.set_verbose(verbose)
    service.start()
    _details()
    out.print(f"OpenSandbox is running at 127.0.0.1:{service.PORT}")


@app.command()
def stop(verbose: VerboseOption = False) -> None:
    """Stop the service."""
    console.set_verbose(verbose)
    out.print("Stopped OpenSandbox" if service.stop() else "OpenSandbox wasn't running")


@app.command()
def status(verbose: VerboseOption = False) -> None:
    """Show the container engine, and whether the service is running."""
    console.set_verbose(verbose)
    try:
        out.print(f"Engine: {engine.name()} at {engine.where()}", highlight=False)
    except Failed as failure:
        out.print(f"Engine: {failure}", highlight=False)
    if service.running():
        out.print(f"OpenSandbox: running at 127.0.0.1:{service.PORT}", highlight=False)
        _details()
    else:
        out.print("OpenSandbox: not running")


def _details() -> None:
    """The running service's process, files, and the config it started with."""
    directory = paths.opensandbox()
    detail(f"Process: {service.pid() or 'not started by avp'}")
    detail(f"Config: {directory / 'config.toml'}")
    detail(f"Log: {directory / 'server.log'}")
    config = service.config() or {}
    egress = config.get("egress", {})
    detail(f"Exec daemon image: {config.get('runtime', {}).get('execd_image', 'not set')}")
    detail(f"Egress image: {egress.get('image', 'not set')}, mode {egress.get('mode', 'not set')}")

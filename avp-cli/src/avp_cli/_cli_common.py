"""Options that more than one command takes."""

from typing import Annotated

import typer

AgentOption = Annotated[str, typer.Option("--agent", help="An installed agent.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print JSON.")]
VerboseOption = Annotated[
    bool, typer.Option("--verbose", help="Print more about what avp does, to stderr.")
]
YesOption = Annotated[
    bool, typer.Option("--yes", "-y", "--force", "-f", help="Don't ask before going ahead.")
]

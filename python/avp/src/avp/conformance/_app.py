"""Typer app for `avp-conformance`. Requires the `conformance` extra.

`ping` is implemented; `run`, `validate`, and `check-coverage` are stubs.
See CONFORMANCE_PLAN.md for the planned behavior of each.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from avp.conformance.manifest import AgentManifest

app = typer.Typer(
    name="avp-conformance",
    help="AVP v0.1 conformance: run cases against an SDK, validate cases, check coverage.",
    no_args_is_help=True,
    add_completion=False,
)


def _load_manifest(path: Path) -> AgentManifest:
    """Load and validate an agent manifest, exiting with a clear error on failure."""
    try:
        return AgentManifest.model_validate_json(path.read_text())
    except FileNotFoundError:
        typer.echo(f"error: manifest not found: {path}", err=True)
        raise typer.Exit(code=2) from None
    except ValidationError as e:
        typer.echo(f"error: manifest invalid:\n{e}", err=True)
        raise typer.Exit(code=2) from None


@app.command()
def ping(
    agent: Annotated[
        Path,
        typer.Option("--agent", help="Path to the agent manifest JSON."),
    ],
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait for the agent's ping response."),
    ] = 10.0,
) -> None:
    """Verify the agent at --agent is invocable and emits {"type": "pong"}."""
    manifest = _load_manifest(agent)
    cwd = (agent.parent / manifest.cwd).resolve()

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        out_path = Path(f.name)

    try:
        cmd = [*manifest.command, "ping", "--out", str(out_path)]
        env = {**os.environ, **manifest.env}
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            typer.echo(f"FAIL  ping  exit={result.returncode}", err=True)
            if result.stderr:
                typer.echo(f"      stderr: {result.stderr[-500:].strip()}", err=True)
            raise typer.Exit(code=1)

        lines = [ln for ln in out_path.read_text().splitlines() if ln.strip()]
        if len(lines) != 1:
            typer.echo(f"FAIL  ping  expected 1 line in --out, got {len(lines)}", err=True)
            raise typer.Exit(code=1)

        try:
            payload = json.loads(lines[0])
        except json.JSONDecodeError as e:
            typer.echo(f"FAIL  ping  --out line is not JSON: {e}", err=True)
            raise typer.Exit(code=1) from None

        if payload != {"type": "pong"}:
            typer.echo(f'FAIL  ping  expected {{"type": "pong"}}, got {payload}', err=True)
            raise typer.Exit(code=1)

        typer.echo("PASS  ping")
    finally:
        out_path.unlink(missing_ok=True)


@app.command()
def run(
    agent: Annotated[
        Path,
        typer.Option("--agent", help="Path to the agent manifest JSON."),
    ],
    suite: Annotated[
        str | None,
        typer.Option("--suite", help="Spec version to run (e.g. 'v0.1')."),
    ] = None,
    case: Annotated[
        Path | None,
        typer.Option("--case", help="Path to a single case file."),
    ] = None,
) -> None:
    """Execute conformance cases against the SDK described by --agent."""
    if suite is None and case is None:
        typer.echo("error: run requires either --suite or --case.", err=True)
        raise typer.Exit(code=2)
    if suite is not None and case is not None:
        typer.echo("error: --suite and --case are mutually exclusive.", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"[stub] run: agent={agent} suite={suite} case={case}")


@app.command()
def validate(
    suite: Annotated[
        str,
        typer.Option("--suite", help="Spec version to validate."),
    ] = "v0.1",
) -> None:
    """Validate every packaged case file against the TestCase pydantic model."""
    typer.echo(f"[stub] validate: suite={suite}")


@app.command("check-coverage")
def check_coverage(
    suite: Annotated[
        str,
        typer.Option("--suite", help="Spec version to check."),
    ] = "v0.1",
) -> None:
    """Assert every event type in the trajectory schema has >=1 case asserting on it."""
    typer.echo(f"[stub] check-coverage: suite={suite}")

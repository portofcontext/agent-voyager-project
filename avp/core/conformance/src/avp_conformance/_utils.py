import json
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from avp.commission import Commission
from avp_conformance.case import AgentBuiltins, TestCase
from avp_conformance.manifest import AgentManifest


def read_json_arg(value: str) -> Any:
    """Parse a CLI arg that accepts either inline JSON or a path to a JSON file.

    Used by agent CLI entrypoints (`--commission`, `--built-in`, etc.) so
    callers can pass `--commission '{"run_id": "x", ...}'` or
    `--commission ./commission.json` interchangeably. Inline JSON is detected
    by a leading `{` or `[` after whitespace; anything else is read as a path.
    """
    value = value.strip()
    if value.startswith(("{", "[")):
        return json.loads(value)
    return json.loads(Path(value).read_text())


def load_commission(value: str) -> Commission:
    """Load and validate a Commission from inline JSON or a path to a JSON file.

    Convenience wrapper that any agent SDK's `run --commission <json|path>`
    handler can call directly. Lets validation errors propagate so callers
    decide how to surface them (argparse traceback vs structured message).
    """
    return Commission.model_validate(read_json_arg(value))


def load_built_in(value: str) -> AgentBuiltins:
    """Load and validate an AgentBuiltins fixture from inline JSON or a path.

    Matches `load_commission` for the optional `--built-in <json|path>` flag.
    """
    return AgentBuiltins.model_validate(read_json_arg(value))


def load_manifest(path: Path) -> AgentManifest:
    """Load and validate an agent manifest, exiting with a clear error on failure."""
    try:
        return AgentManifest.model_validate_json(path.read_text())
    except FileNotFoundError:
        typer.echo(f"error: manifest not found: {path}", err=True)
        raise typer.Exit(code=2) from None
    except ValidationError as e:
        typer.echo(f"error: manifest invalid:\n{e}", err=True)
        raise typer.Exit(code=2) from None


def load_case(source: Path | Traversable, label: str) -> TestCase:
    """Load and validate one case file. `label` is used in the error message."""
    try:
        return TestCase.model_validate_json(source.read_text())
    except FileNotFoundError:
        typer.echo(f"error: case not found: {label}", err=True)
        raise typer.Exit(code=2) from None
    except ValidationError as e:
        typer.echo(f"error: case {label} invalid:\n{e}", err=True)
        raise typer.Exit(code=2) from None


def discover_suite(suite: str) -> dict[str, list[TestCase]]:
    """Load every packaged case for `suite`, grouped by category subdir name.

    Category subdirs are direct children of `cases/<suite>/`.
    """
    root = files("avp_conformance") / "cases" / suite
    if not root.is_dir():
        typer.echo(f"error: suite '{suite}' not found in packaged cases", err=True)
        raise typer.Exit(code=2) from None

    grouped: dict[str, list[TestCase]] = {}
    for category in sorted(root.iterdir(), key=lambda t: t.name):
        if not category.is_dir():
            continue
        cases: list[TestCase] = []
        for entry in sorted(category.iterdir(), key=lambda t: t.name):
            if entry.is_file() and entry.name.endswith(".json"):
                cases.append(load_case(entry, f"{category.name}/{entry.name}"))
        if cases:
            grouped[category.name] = cases
    return grouped

"""Typer app for `avp-conformance`. Requires the `conformance` extra.

`ping`, `validate`, and `check` are implemented end-to-end. `check` writes
each case's Commission (and optional built-in fixture) to temp files, spawns
the agent's `run` subcommand per the manifest, reads the emitted NDJSON
trajectory, and matches it against the case's expectations.

`--sandbox` wraps the agent invocation in `srt`
(@anthropic-ai/sandbox-runtime) so a live run's shell tools can only write to
the run's scratch dirs and reach only the model provider's API.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from avp_conformance._match import match_case
from avp_conformance._utils import discover_suite, load_case, load_manifest
from avp_conformance.case import TestCase
from avp_conformance.manifest import AgentManifest

app = typer.Typer(
    name="avp-conformance",
    help="AVP v0.1 conformance: run cases against an SDK, validate cases, check coverage.",
    no_args_is_help=True,
    add_completion=False,
)


# ── Subprocess + sandbox plumbing ──────────────────────────────────────────────


def _resolve_cwd(agent: Path, manifest: AgentManifest) -> Path:
    """Manifest `cwd` is relative to the manifest file, not the caller's CWD."""
    return (agent.parent / manifest.cwd).resolve()


def _sandbox_prefix(sandbox: bool, cwd: Path, stack: list[Path]) -> list[str]:
    """Build the `srt --settings <profile>` command prefix, or [] when off.

    The packaged base profile is deny-by-default network + filesystem; the
    writable allow-list is computed here (the OS temp dir, `/tmp`, and the
    agent's cwd) because that's where the run's scratch and the harness's
    temp Commission/--out files live. Errors out if `srt` isn't installed.
    `stack` collects temp settings files for the caller to clean up.
    """
    if not sandbox:
        return []
    srt = shutil.which("srt")
    if srt is None:
        typer.echo(
            "error: --sandbox needs the `srt` CLI (npm install -g @anthropic-ai/sandbox-runtime)",
            err=True,
        )
        raise typer.Exit(code=2)

    base = json.loads((files("avp_conformance") / "sandbox-profile.json").read_text())
    base.pop("_comment", None)
    tmpdir = tempfile.gettempdir()
    write = base.setdefault("filesystem", {}).setdefault("allowWrite", [])
    for path in (tmpdir, "/tmp", str(cwd)):
        if path not in write:
            write.append(path)

    fd, settings_path = tempfile.mkstemp(suffix=".srt-settings.json")
    with os.fdopen(fd, "w") as f:
        json.dump(base, f)
    stack.append(Path(settings_path))
    return [srt, "--settings", settings_path]


# ── ping ────────────────────────────────────────────────────────────────────


@app.command()
def ping(
    agent: Annotated[
        Path,
        typer.Option("--agent", help="Path to the agent manifest JSON."),
    ],
    sandbox: Annotated[
        bool,
        typer.Option("--sandbox/--no-sandbox", help="Wrap the agent in `srt` sandbox."),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait for the agent's ping response."),
    ] = 10.0,
) -> None:
    """Verify the agent at --agent is invocable and emits {"type": "pong"}."""
    manifest = load_manifest(agent)
    cwd = _resolve_cwd(agent, manifest)
    cleanup: list[Path] = []

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        out_path = Path(f.name)

    try:
        prefix = _sandbox_prefix(sandbox, cwd, cleanup)
        cmd = [*prefix, *manifest.command, "ping", "--out", str(out_path)]
        env = {**os.environ, **manifest.env}
        result = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
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
        for path in cleanup:
            path.unlink(missing_ok=True)


# ── check ─────────────────────────────────────────────────────────────────────


def _run_case(
    tc: TestCase,
    manifest: AgentManifest,
    cwd: Path,
    prefix: list[str],
    timeout: float,
) -> tuple[list[dict] | None, str | None]:
    """Spawn the agent's `run` for one case; return (events, error).

    On success `error` is None and `events` is the parsed NDJSON trajectory.
    On failure `events` is None and `error` is a one-line diagnostic.
    """
    env = {**os.environ, **manifest.env}
    with tempfile.TemporaryDirectory(prefix=f"avp-case-{tc.id}-") as tmp:
        tmpd = Path(tmp)
        commission_path = tmpd / "commission.json"
        commission_path.write_text(tc.commission.model_dump_json(by_alias=True, exclude_none=True))
        out_path = tmpd / "out.jsonl"

        args = ["run", "--commission", str(commission_path)]
        if tc.built_in is not None:
            built_in_path = tmpd / "built-in.json"
            built_in_path.write_text(tc.built_in.model_dump_json(by_alias=True, exclude_none=True))
            args += ["--built-in", str(built_in_path)]
        args += ["--out", str(out_path)]

        cmd = [*prefix, *manifest.command, *args]
        try:
            result = subprocess.run(
                cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return None, f"timed out after {timeout}s"

        if result.returncode != 0:
            tail = result.stderr[-500:].strip() if result.stderr else "(no stderr)"
            return None, f"agent exit={result.returncode}: {tail}"

        if not out_path.exists():
            return None, "agent wrote no --out file"
        events = [json.loads(ln) for ln in out_path.read_text().splitlines() if ln.strip()]
        return events, None


@app.command()
def check(
    agent: Annotated[
        Path,
        typer.Option("--agent", help="Path to the agent manifest JSON."),
    ],
    suite: Annotated[
        str | None,
        typer.Option("--suite", help="Spec version to check (e.g. 'v0.1')."),
    ] = None,
    case: Annotated[
        Path | None,
        typer.Option("--case", help="Path to a single case file."),
    ] = None,
    sandbox: Annotated[
        bool,
        typer.Option("--sandbox/--no-sandbox", help="Wrap each agent run in `srt` sandbox."),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait for each case's agent run."),
    ] = 120.0,
) -> None:
    """Run conformance cases against the SDK described by --agent."""
    if suite is None and case is None:
        typer.echo("error: check requires either --suite or --case.", err=True)
        raise typer.Exit(code=2)
    if suite is not None and case is not None:
        typer.echo("error: --suite and --case are mutually exclusive.", err=True)
        raise typer.Exit(code=2)

    manifest = load_manifest(agent)
    cwd = _resolve_cwd(agent, manifest)

    if case is not None:
        grouped = {case.parent.name: [load_case(case, str(case))]}
    else:
        assert suite is not None  # narrowed by the guards above
        grouped = discover_suite(suite)

    total = sum(len(cs) for cs in grouped.values())
    if total == 0:
        typer.echo("error: no cases found to check.", err=True)
        raise typer.Exit(code=2)

    cleanup: list[Path] = []
    n_pass = 0
    n_fail = 0
    try:
        prefix = _sandbox_prefix(sandbox, cwd, cleanup)
        typer.echo(f"running {total} case(s) against {manifest.command[0]!r}\n")
        for cat_name in sorted(grouped):
            typer.echo(f"  {cat_name}:")
            for tc in grouped[cat_name]:
                events, error = _run_case(tc, manifest, cwd, prefix, timeout)
                if error is not None:
                    typer.echo(f"    FAIL  {tc.id}  {error}", err=True)
                    n_fail += 1
                    continue
                assert events is not None
                result = match_case(events, tc.expectations)
                if result.ok:
                    typer.echo(f"    PASS  {tc.id}")
                    n_pass += 1
                else:
                    typer.echo(f"    FAIL  {tc.id}", err=True)
                    for reason in result.reasons:
                        typer.echo(f"          {reason}", err=True)
                    n_fail += 1
    finally:
        for path in cleanup:
            path.unlink(missing_ok=True)

    typer.echo(f"\nchecked {total} case(s) ({n_pass} pass, {n_fail} fail)")
    if n_fail > 0:
        raise typer.Exit(code=1)


# ── validate ──────────────────────────────────────────────────────────────────


@app.command()
def validate(
    suite: Annotated[
        str,
        typer.Option("--suite", help="Spec version to validate."),
    ] = "v0.1",
) -> None:
    """Validate every packaged case file against the TestCase pydantic model.

    Walks `cases/<suite>/<category>/*.json` and reports per-file pass / fail.
    Exits 0 if every case validates (including an empty suite), 1 if any
    case fails, 2 if the suite dir is missing.
    """
    root = files("avp_conformance") / "cases" / suite
    if not root.is_dir():
        typer.echo(f"error: suite '{suite}' not found in packaged cases", err=True)
        raise typer.Exit(code=2)

    n_pass = 0
    n_fail = 0
    for category in sorted(root.iterdir(), key=lambda t: t.name):
        if not category.is_dir():
            continue
        for entry in sorted(category.iterdir(), key=lambda t: t.name):
            if not (entry.is_file() and entry.name.endswith(".json")):
                continue
            label = f"{category.name}/{entry.name}"
            try:
                TestCase.model_validate_json(entry.read_text())
                typer.echo(f"PASS  {label}")
                n_pass += 1
            except ValidationError as e:
                typer.echo(f"FAIL  {label}", err=True)
                for line in str(e).splitlines():
                    typer.echo(f"      {line}", err=True)
                n_fail += 1

    total = n_pass + n_fail
    typer.echo(f"\nvalidated {total} case(s) ({n_pass} pass, {n_fail} fail)")
    if n_fail > 0:
        raise typer.Exit(code=1)

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
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from avp.descriptor import AgentDescriptor
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


# Domains the sandboxed agents (and their build toolchains) reach: the Anthropic
# model API, plus github for cargo's git-sourced deps (goose pins `block/goose`).
# srt forbids a bare "*", so this is an explicit (generous) allow-list; extend it
# per run with `check --allow-domain`. Network isn't the security lever here
# (writes are) — this list just keeps the agents from failing to connect.
_DEFAULT_ALLOW_DOMAINS = (
    "api.anthropic.com",
    "*.anthropic.com",
    "github.com",
    "codeload.github.com",
)

# macOS native-tls (goose's reqwest) resolves cert trust via this Mach service;
# srt blocks it by default, so the agent can't establish TLS. Linux ignores it.
_MACOS_TRUST_MACH_SERVICE = "com.apple.trustd.agent"


def _toolchain_write_dirs() -> list[str]:
    """Existing build-toolchain dirs the launcher (`uv run` / `cargo run`) must
    WRITE under the sandbox: uv's cache, cargo's home (git checkouts/locks), and
    rustup's home (the cargo shim writes settings.toml). Reads are open, so these
    only need to be on the write allow-list. Honors UV_CACHE_DIR / CARGO_HOME /
    RUSTUP_HOME overrides."""
    home = Path.home()
    candidates = [
        os.environ.get("UV_CACHE_DIR"),
        home / "Library" / "Caches" / "uv",  # macOS default
        home / ".cache" / "uv",  # Linux default
        os.environ.get("CARGO_HOME"),
        home / ".cargo",
        os.environ.get("RUSTUP_HOME"),
        home / ".rustup",
    ]
    return [str(Path(c)) for c in candidates if c and Path(c).exists()]


def _repo_root(start: Path) -> Path:
    """Nearest ancestor of `start` containing `.git`, else `start`."""
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return start


def _expand_fixture_tokens(
    commission_json: str, cwd: Path, identity: tuple[str, str] | None = None
) -> str:
    """Expand in-repo fixture placeholders in a serialized Commission so a case
    can reference repo fixtures portably (their absolute path differs per
    checkout). `${AVP_TEST_MCP}` → the bundled stdio test MCP server at
    `testing/mcp/avp_test_mcp.py`. `${AGENT_NAME}` / `${AGENT_VERSION}` → the
    agent-under-test's descriptor identity, so cases can key the per-agent
    `enabled_builtin_*` / `agent_versions` maps portably across agents."""
    test_mcp = _repo_root(cwd) / "testing" / "mcp" / "avp_test_mcp.py"
    out = commission_json.replace("${AVP_TEST_MCP}", str(test_mcp))
    if identity is not None:
        name, version = identity
        out = out.replace("${AGENT_NAME}", name).replace("${AGENT_VERSION}", version)
    return out


def _describe_identity(
    manifest: AgentManifest, command: list[str], cwd: Path, prefix: list[str], timeout: float
) -> tuple[str, str]:
    """The agent-under-test's `(agent_name, agent_version)` from its pre-flight
    `describe` surface. Cases key per-agent Commission maps with these via the
    `${AGENT_NAME}` / `${AGENT_VERSION}` fixture tokens; `describe` is a
    first-class agent contract, so failure here aborts the check loudly."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_path = Path(f.name)
    try:
        cmd = [*prefix, *command, "describe", "--out", str(out_path)]
        env = {**os.environ, **manifest.env}
        result = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            tail = result.stderr[-300:].strip() if result.stderr else "(no stderr)"
            raise RuntimeError(f"describe exit={result.returncode}: {tail}")
        descriptor = AgentDescriptor.model_validate(json.loads(out_path.read_text()))
        return descriptor.agent_name, descriptor.agent_version
    finally:
        out_path.unlink(missing_ok=True)


def _resolve_command(command: list[str]) -> list[str]:
    """Resolve the launcher (`command[0]`) to an absolute host path so the
    sandbox runs the same binary the host would. srt sets its own PATH, which
    can otherwise resolve a bare `uv`/`cargo` to a different (often stale)
    binary (e.g. `~/.cargo/bin/uv` shadowing `~/.local/bin/uv`)."""
    exe = shutil.which(command[0])
    return [exe, *command[1:]] if exe else command


def _sandbox_prefix(
    sandbox: bool,
    cwd: Path,
    stack: list[Path],
    allow_domains: list[str] | None = None,
) -> list[str]:
    """Build the `srt --settings <profile>` command prefix, or [] when off.

    The one security lever that matters here is WRITES: the sandbox exists to
    stop a model-driven agent from trashing the local checkout/machine, not to
    contain a determined adversary. Reads stay open; network is a generous
    allow-list (srt mandates one). On top of the skeleton the harness allows:

    - writes: an OS-temp scratch (agent workspace + the harness's temp
      Commission/--out files), the build-toolchain dirs the launcher must write
      (uv cache, cargo/rustup home), and the cargo `target/` under cwd. Repo
      source and the rest of the host stay read-only.
    - network: the default allow-list plus any `--allow-domain` extras. On
      macOS, allow the trust Mach service so native-tls clients (goose's
      reqwest) can verify certs.

    Errors out if `srt` isn't installed. `stack` collects temp settings files
    for the caller to clean up.
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

    net = base.setdefault("network", {})
    # Extend (not replace) the defaults so the provider + cargo-git hosts stay
    # reachable even when the caller adds domains.
    net["allowedDomains"] = list(dict.fromkeys([*_DEFAULT_ALLOW_DOMAINS, *(allow_domains or [])]))
    if sys.platform == "darwin":
        net["allowMachLookup"] = [_MACOS_TRUST_MACH_SERVICE]

    write = base.setdefault("filesystem", {}).setdefault("allowWrite", [])
    for p in [tempfile.gettempdir(), *_toolchain_write_dirs(), str(cwd / "target")]:
        if p not in write:
            write.append(p)

    fd, settings_path = tempfile.mkstemp(suffix=".srt-settings.json")
    with os.fdopen(fd, "w") as f:
        json.dump(base, f)
    stack.append(Path(settings_path))
    # `--` stops srt's own option parsing: without it, srt's commander eats
    # flags from the agent command (e.g. uv's `--no-sync`, a tool's `-c`).
    return [srt, "--settings", settings_path, "--"]


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
    command = _resolve_command(manifest.command)
    cleanup: list[Path] = []

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        out_path = Path(f.name)

    try:
        prefix = _sandbox_prefix(sandbox, cwd, cleanup)
        cmd = [*prefix, *command, "ping", "--out", str(out_path)]
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


# ── describe ──────────────────────────────────────────────────────────────────


@app.command()
def describe(
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
        typer.Option("--timeout", help="Seconds to wait for the agent's describe."),
    ] = 60.0,
) -> None:
    """Verify the agent at --agent emits a spec-valid AgentDescriptor from `describe`.

    The pre-flight contract every agent must honor (alongside `ping`/`run`): a
    free, no-model `describe` that prints its capability surface. Validated
    against the `AgentDescriptor` spec model.
    """
    manifest = load_manifest(agent)
    cwd = _resolve_cwd(agent, manifest)
    command = _resolve_command(manifest.command)
    cleanup: list[Path] = []

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_path = Path(f.name)

    try:
        prefix = _sandbox_prefix(sandbox, cwd, cleanup)
        cmd = [*prefix, *command, "describe", "--out", str(out_path)]
        env = {**os.environ, **manifest.env}
        result = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
        )

        if result.returncode != 0:
            typer.echo(f"FAIL  describe  exit={result.returncode}", err=True)
            if result.stderr:
                typer.echo(f"      stderr: {result.stderr[-500:].strip()}", err=True)
            raise typer.Exit(code=1)

        try:
            payload = json.loads(out_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            typer.echo(f"FAIL  describe  --out is not JSON: {e}", err=True)
            raise typer.Exit(code=1) from None

        try:
            descriptor = AgentDescriptor.model_validate(payload)
        except ValidationError as e:
            typer.echo("FAIL  describe  --out is not a valid AgentDescriptor:", err=True)
            for line in str(e).splitlines():
                typer.echo(f"      {line}", err=True)
            raise typer.Exit(code=1) from None

        n_tools = len(descriptor.tools or [])
        typer.echo(
            f"PASS  describe  {descriptor.agent_name} v{descriptor.agent_version} "
            f"({n_tools} tool{'s' if n_tools != 1 else ''})"
        )
    finally:
        out_path.unlink(missing_ok=True)
        for path in cleanup:
            path.unlink(missing_ok=True)


# ── check ─────────────────────────────────────────────────────────────────────


def _run_case(
    tc: TestCase,
    manifest: AgentManifest,
    command: list[str],
    cwd: Path,
    prefix: list[str],
    timeout: float,
    dump_dir: Path | None = None,
    identity: tuple[str, str] | None = None,
) -> tuple[list[dict] | None, str | None]:
    """Spawn the agent's `run` for one case; return (events, error).

    On success `error` is None and `events` is the parsed NDJSON trajectory.
    On failure `events` is None and `error` is a one-line diagnostic.
    When `dump_dir` is set, the emitted trajectory is also saved to
    `<dump_dir>/<case_id>.jsonl` for inspection (whether or not it matches).
    """
    env = {**os.environ, **manifest.env}
    with tempfile.TemporaryDirectory(prefix=f"avp-case-{tc.id}-") as tmp:
        tmpd = Path(tmp)
        commission_path = tmpd / "commission.json"
        commission_json = _expand_fixture_tokens(
            tc.commission.model_dump_json(by_alias=True, exclude_none=True), cwd, identity
        )
        commission_path.write_text(commission_json)
        out_path = tmpd / "out.jsonl"

        args = ["run", "--commission", str(commission_path)]
        if tc.built_in is not None:
            built_in_path = tmpd / "built-in.json"
            built_in_path.write_text(tc.built_in.model_dump_json(by_alias=True, exclude_none=True))
            args += ["--built-in", str(built_in_path)]
        args += ["--out", str(out_path)]

        cmd = [*prefix, *command, *args]
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
        raw = out_path.read_text()
        if dump_dir is not None:
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / f"{tc.id}.jsonl").write_text(raw)
            # Agent stderr is free-form logging; capture it too so a clean
            # exit-0 run with a suspicious trajectory can still be debugged.
            (dump_dir / f"{tc.id}.stderr").write_text(result.stderr or "")
        events = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
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
    dump_dir: Annotated[
        Path | None,
        typer.Option("--dump-dir", help="Save each emitted trajectory to <dir>/<case_id>.jsonl."),
    ] = None,
    allow_domain: Annotated[
        list[str] | None,
        typer.Option(
            "--allow-domain",
            help="Domain the sandboxed agent may reach (repeatable). Defaults to the Anthropic API.",
        ),
    ] = None,
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
    command = _resolve_command(manifest.command)

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
        prefix = _sandbox_prefix(sandbox, cwd, cleanup, allow_domain)
        try:
            identity = _describe_identity(manifest, command, cwd, prefix, timeout)
        except Exception as exc:
            typer.echo(f"error: could not learn the agent's identity via describe: {exc}", err=True)
            raise typer.Exit(code=2) from None
        typer.echo(
            f"running {total} case(s) against {manifest.command[0]!r} "
            f"({identity[0]} v{identity[1]})\n"
        )
        for cat_name in sorted(grouped):
            typer.echo(f"  {cat_name}:")
            for tc in grouped[cat_name]:
                events, error = _run_case(
                    tc, manifest, command, cwd, prefix, timeout, dump_dir, identity
                )
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

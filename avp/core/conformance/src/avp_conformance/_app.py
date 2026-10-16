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
import signal
import subprocess
import sys
import tempfile
import time
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from avp.descriptor import AgentDescriptor
from avp.launch import local_environment
from avp_conformance._match import MatchResult, match_case
from avp_conformance._meter import Meter, reconcile
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
    `testing/mcp/avp_test_mcp.py`; `${AVP_TEST_PYTHON}` → this harness's Python
    interpreter. `${AGENT_NAME}` / `${AGENT_VERSION}` → the
    agent-under-test's descriptor identity, so cases can key the per-agent
    `enabled_builtin_*` / `agent_versions` maps portably across agents."""
    test_mcp = _repo_root(cwd) / "testing" / "mcp" / "avp_test_mcp.py"
    out = commission_json.replace("${AVP_TEST_MCP}", str(test_mcp))
    out = out.replace("${AVP_TEST_PYTHON}", sys.executable)
    if identity is not None:
        name, version = identity
        out = out.replace("${AGENT_NAME}", name).replace("${AGENT_VERSION}", version)
    return out


def _describe_agent(
    manifest: AgentManifest,
    command: list[str],
    cwd: Path,
    prefix: list[str],
    timeout: float,
    extra_env: dict[str, str] | None = None,
) -> AgentDescriptor:
    """The agent-under-test's pre-flight `describe` descriptor. Its identity
    keys per-agent Commission maps via the `${AGENT_NAME}` / `${AGENT_VERSION}`
    fixture tokens, and its declared surfaces decide which cases apply
    (`TestCase.requires`). `describe` is a first-class agent contract, so
    failure here aborts the check loudly."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_path = Path(f.name)
    try:
        cmd = [*prefix, *command, "describe", "--out", str(out_path)]
        with local_environment({**manifest.env, **(extra_env or {})}) as env:
            result = subprocess.run(
                cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout
            )
        if result.returncode != 0:
            tail = result.stderr[-300:].strip() if result.stderr else "(no stderr)"
            raise RuntimeError(f"describe exit={result.returncode}: {tail}")
        return AgentDescriptor.model_validate(json.loads(out_path.read_text()))
    finally:
        out_path.unlink(missing_ok=True)


# Credential variables per model origin, for `credentials: "invalid"` cases.
# The first is set to a well-formed but invalid key; every one is overridden,
# and the alternates listed in `_ALT_CREDENTIALS` are removed, so no fallback
# credential (an OAuth token, a second key name) rescues the run.
_CREDENTIAL_VARS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY", "CODEX_API_KEY"),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "mistral": ("MISTRAL_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
}
_ALT_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
}
_INVALID_KEY = "sk-avp-conformance-invalid-0000000000000000000000000000"


def _invalid_credentials(env: dict[str, str], model: str) -> dict[str, str]:
    """`env` with the model provider's credentials replaced by an invalid key."""
    origin = model.split("/", 1)[0]
    names = _CREDENTIAL_VARS.get(origin)
    if names is None:
        raise ValueError(f"no known credential variables for model origin {origin!r}")
    out = {k: v for k, v in env.items() if k not in _ALT_CREDENTIALS.get(origin, ())}
    out.update(dict.fromkeys(names, _INVALID_KEY))
    return out


# API hosts a `--model` origin needs when the run is sandboxed (`--sandbox`).
_PROVIDER_DOMAINS: dict[str, tuple[str, ...]] = {
    "openai": ("api.openai.com",),
    "google": ("generativelanguage.googleapis.com",),
    "mistral": ("api.mistral.ai",),
    "openrouter": ("openrouter.ai",),
}


def with_model(tc: TestCase, model: str) -> TestCase:
    """Rewrite the fixture model and its native provider, including expectations.

    A native provider follows a change of model origin. Explicit gateways or
    endpoint overrides retain their routing. Vault handles are opaque fixture
    data and are preserved; credential injection belongs to the launcher.
    """
    pinned = json.dumps(tc.commission.model)
    raw = tc.model_dump_json(by_alias=True, exclude_none=True)
    data = json.loads(raw.replace(pinned, json.dumps(model)))
    provider = tc.commission.provider
    old_origin = tc.commission.model.split("/", 1)[0]
    if provider is not None and provider.id == old_origin and provider.base_url is None:
        new_origin = model.split("/", 1)[0]

        def rewrite_provider(value):
            if isinstance(value, dict):
                route = value.get("provider")
                if (
                    isinstance(route, dict)
                    and route.get("id") == old_origin
                    and not route.get("base_url")
                ):
                    route["id"] = new_origin
                for child in value.values():
                    rewrite_provider(child)
            elif isinstance(value, list):
                for child in value:
                    rewrite_provider(child)

        rewrite_provider(data)
    return TestCase.model_validate(data)


def unmet_requirements(tc: TestCase, descriptor: AgentDescriptor) -> list[str]:
    """The `requires` surfaces the agent's descriptor doesn't declare."""
    return [r for r in tc.requires if not getattr(descriptor, r)]


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
        with local_environment(manifest.env) as env:
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
        with local_environment(manifest.env) as env:
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
    extra_env: dict[str, str] | None = None,
) -> tuple[list[dict] | None, str | None]:
    """Spawn the agent's `run` for one case; return (events, error).

    On success `error` is None and `events` is the parsed NDJSON trajectory.
    On failure `events` is None and `error` is a one-line diagnostic.
    When `dump_dir` is set, the emitted trajectory is also saved to
    `<dump_dir>/<case_id>.jsonl` for inspection (whether or not it matches).
    """
    with (
        tempfile.TemporaryDirectory(prefix=f"avp-case-{tc.id}-") as tmp,
        local_environment({**manifest.env, **(extra_env or {})}) as env,
    ):
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

        if tc.credentials == "invalid":
            try:
                env = _invalid_credentials(env, tc.commission.model)
            except ValueError as exc:
                return None, str(exc)

        cmd = [*prefix, *command, *args]
        stderr_path = tmpd / "stderr.txt"
        with stderr_path.open("w") as stderr:
            proc = subprocess.Popen(
                cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=stderr, text=True
            )
            try:
                if tc.interrupt is not None and (error := _interrupt(proc, tc, out_path, timeout)):
                    proc.kill()
                    proc.wait()
                    return None, error
                returncode = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                return None, f"timed out after {timeout}s"
        stderr_text = stderr_path.read_text()

        # An interrupted agent's exit status is its own business; its
        # trajectory is what the case judges.
        if returncode != 0 and tc.interrupt is None:
            tail = stderr_text[-500:].strip() or "(no stderr)"
            return None, f"agent exit={returncode}: {tail}"

        if not out_path.exists():
            return None, "agent wrote no --out file"
        raw = out_path.read_text()
        if dump_dir is not None:
            dump_dir.mkdir(parents=True, exist_ok=True)
            (dump_dir / f"{tc.id}.jsonl").write_text(raw)
            # Agent stderr is free-form logging; capture it too so a clean
            # exit-0 run with a suspicious trajectory can still be debugged.
            (dump_dir / f"{tc.id}.stderr").write_text(stderr_text)
        events = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
        return events, None


def _interrupt(proc: subprocess.Popen, tc: TestCase, out_path: Path, timeout: float) -> str | None:
    """Wait for `tc.interrupt.after` on the trajectory, then signal the agent.
    Returns an error when the agent exits or times out before that point."""
    assert tc.interrupt is not None
    deadline = time.monotonic() + timeout
    while not _has_event(out_path, tc.interrupt.after):
        if proc.poll() is not None:
            return f"agent exited before {tc.interrupt.after} (nothing to interrupt)"
        if time.monotonic() > deadline:
            return f"timed out after {timeout}s waiting for {tc.interrupt.after}"
        time.sleep(0.05)
    time.sleep(tc.interrupt.delay_s)
    if proc.poll() is not None:
        return f"agent finished within {tc.interrupt.delay_s}s of {tc.interrupt.after}"
    proc.send_signal(getattr(signal, tc.interrupt.signal))
    return None


def _has_event(out_path: Path, event_type: str) -> bool:
    try:
        text = out_path.read_text()
    except OSError:
        return False
    for line in text.splitlines():
        try:
            if json.loads(line).get("type") == event_type:
                return True
        except json.JSONDecodeError:
            continue  # a line still being written
    return False


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
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Run every case on this model slug (e.g. 'openai/gpt-4o-mini') instead of "
            "the one the case pins. Rewritten throughout the case, expectations included.",
        ),
    ] = None,
    meter: Annotated[
        bool,
        typer.Option(
            "--meter/--no-meter",
            help="Route provider traffic through a local metering proxy and fail a case whose "
            "trajectory omits tokens the provider billed (and a describe that calls a model). "
            "It sets the provider endpoint variables; use --no-meter to keep your own.",
        ),
    ] = True,
) -> None:
    """Run conformance cases against the SDK described by --agent.

    A case whose `requires` names a surface the agent's descriptor doesn't
    declare is reported SKIP and doesn't fail the check."""
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
    if model is not None:
        grouped = {cat: [with_model(tc, model) for tc in cases] for cat, cases in grouped.items()}
        origin = model.split("/", 1)[0]
        allow_domain = [*(allow_domain or []), *_PROVIDER_DOMAINS.get(origin, ())]

    total = sum(len(cs) for cs in grouped.values())
    if total == 0:
        typer.echo("error: no cases found to check.", err=True)
        raise typer.Exit(code=2)

    cleanup: list[Path] = []
    n_pass = 0
    n_fail = 0
    n_skip = 0
    metering = Meter().start() if meter else None
    routing = metering.env() if metering else {}
    if metering is not None and sandbox:
        allow_domain = [*(allow_domain or []), "localhost", "127.0.0.1"]
    try:
        prefix = _sandbox_prefix(sandbox, cwd, cleanup, allow_domain)
        try:
            descriptor = _describe_agent(manifest, command, cwd, prefix, timeout, routing)
        except Exception as exc:
            typer.echo(f"error: could not learn the agent's identity via describe: {exc}", err=True)
            raise typer.Exit(code=2) from None
        identity = (descriptor.agent_name, descriptor.agent_version)
        typer.echo(
            f"running {total} case(s) against {manifest.command[0]!r} "
            f"({identity[0]} v{identity[1]})\n"
        )
        if metering is not None and (billed := metering.take()):
            typer.echo(
                f"  FAIL  describe called a model ({len(billed)} billed response(s)); "
                "describe must be free",
                err=True,
            )
            n_fail += 1
        for cat_name in sorted(grouped):
            typer.echo(f"  {cat_name}:")
            for tc in grouped[cat_name]:
                if missing := unmet_requirements(tc, descriptor):
                    typer.echo(f"    SKIP  {tc.id}  (agent declares no {', '.join(missing)})")
                    n_skip += 1
                    continue
                if metering is not None:
                    metering.take()
                events, error = _run_case(
                    tc, manifest, command, cwd, prefix, timeout, dump_dir, identity, routing
                )
                if error is not None:
                    typer.echo(f"    FAIL  {tc.id}  {error}", err=True)
                    n_fail += 1
                    continue
                assert events is not None
                result = match_case(events, tc.expectations)
                if metering is not None and (unbilled := reconcile(metering.take(), events)):
                    result = MatchResult(ok=False, reasons=[*result.reasons, *unbilled])
                if result.ok:
                    typer.echo(f"    PASS  {tc.id}")
                    n_pass += 1
                else:
                    typer.echo(f"    FAIL  {tc.id}", err=True)
                    for reason in result.reasons:
                        typer.echo(f"          {reason}", err=True)
                    n_fail += 1
    finally:
        if metering is not None:
            metering.stop()
        for path in cleanup:
            path.unlink(missing_ok=True)

    typer.echo(f"\nchecked {total} case(s) ({n_pass} pass, {n_fail} fail, {n_skip} skip)")
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

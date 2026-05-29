"""The agents an eval can run against: Goose and Claude Code.

Each is just its `avp-conformance.json` manifest, the same one the conformance
harness drives. An agent can come from one of three places, tried in order by
`resolve_agent`:

1. **An explicit manifest path** (`--agent path/to/avp-conformance.json`) for
   any third-party agent, no code change.
2. **An installed agent** under `~/.avp/agents/<name>/` (a prebuilt artifact laid
   down by `avp agent install`). This is the normal path once published.
3. **The in-repo dev fallback** (`agents/<name>/<lang>/avp-conformance.json`),
   used only when running from a source checkout. Its manifest builds the agent
   from source (`cargo run` / `uv run`), so it's slow and needs the toolchain.

`AGENT_SOURCES` describes, per known agent, how it's distributed (a prebuilt
binary vs. a Python wheel set) and where its dev-fallback manifest lives; the
installer (`avp_cli.agent_install`) consumes it. `preflight` reports why an agent
can't run locally so the CLI can skip cleanly instead of erroring.
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from avp_conformance.manifest import AgentManifest

from avp_cli import paths
from avp_cli.agent import load_manifest


@dataclass(frozen=True)
class AgentSource:
    """How a known agent is distributed and how the CLI installs / falls back to it.

    `kind` selects the install mechanism: `"binary"` (a prebuilt executable
    extracted to `bin/`) or `"python"` (a wheel set installed into a managed
    `venv/`). `tag_prefix` is the GitHub release tag stem (`agent-goose` →
    `agent-goose-v0.0.1`). `dev_manifest` is the in-repo manifest used only from
    a source checkout.
    """

    name: str
    kind: str  # "binary" | "python"
    tag_prefix: str
    dev_manifest: str
    # binary agents
    binary_name: str | None = None
    # python agents: `python -m <module>`, install `dist` (pulls third-party
    # deps from PyPI), with `wheel_dists` the unpublished in-repo wheels shipped
    # on the release (resolved via --find-links so PyPI's unrelated `avp` isn't).
    module: str | None = None
    dist: str | None = None
    wheel_dists: tuple[str, ...] = field(default_factory=tuple)


AGENT_SOURCES: dict[str, AgentSource] = {
    "goose": AgentSource(
        name="goose",
        kind="binary",
        tag_prefix="agent-goose",
        dev_manifest="agents/avp-goose/rust/avp-conformance.json",
        binary_name="avp-goose-conformance",
    ),
    "claude-code": AgentSource(
        name="claude-code",
        kind="python",
        tag_prefix="agent-claude-code",
        dev_manifest="agents/avp-claude-agent-sdk/python/avp-conformance.json",
        module="avp_claude_agent_sdk.conformance",
        dist="avp-claude-agent-sdk",
        # The conformance entrypoint also imports avp_conformance (load_commission
        # / load_built_in), which pulls avp + typer; ship all the in-repo wheels.
        wheel_dists=("avp", "avp-conformance", "avp-claude-agent-sdk"),
    ),
}

DEFAULT_AGENT = "claude-code"


def _repo_root() -> Path:
    # .../avp-cli/src/avp_cli/agents.py -> repo root
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ResolvedAgent:
    name: str
    manifest: AgentManifest
    manifest_cwd: Path


def known_agents() -> list[str]:
    return list(AGENT_SOURCES)


def installed_manifest_path(name: str) -> Path:
    """Where an installed agent's generated manifest lives (may not exist)."""
    return paths.agents_dir() / name / "avp-conformance.json"


def is_installed(name: str) -> bool:
    return installed_manifest_path(name).is_file()


def has_dev_fallback(name: str) -> bool:
    """True if a known agent's in-repo manifest exists (running from a checkout)."""
    src = AGENT_SOURCES.get(name)
    return src is not None and (_repo_root() / src.dev_manifest).is_file()


def resolve_agent(spec: str) -> ResolvedAgent:
    """Resolve a known agent name or a manifest path to a runnable agent."""
    if spec in AGENT_SOURCES:
        return _resolve_known(spec)
    # Arbitrary third-party agent: spec is a path to its manifest.
    path = Path(spec)
    if not path.is_file():
        raise SystemExit(f"agent manifest not found: {path}")
    manifest, cwd = load_manifest(path)
    return ResolvedAgent(name=path.parent.name or spec, manifest=manifest, manifest_cwd=cwd)


def _resolve_known(name: str) -> ResolvedAgent:
    """Installed agent first, then the in-repo dev fallback."""
    installed = installed_manifest_path(name)
    if installed.is_file():
        manifest, cwd = load_manifest(installed)
        return ResolvedAgent(name=name, manifest=manifest, manifest_cwd=cwd)
    dev = _repo_root() / AGENT_SOURCES[name].dev_manifest
    if dev.is_file():
        manifest, cwd = load_manifest(dev)
        return ResolvedAgent(name=name, manifest=manifest, manifest_cwd=cwd)
    raise SystemExit(
        f"agent '{name}' is not installed and no in-repo copy was found.\n"
        f"  install it:             avp agent install {name}\n"
        f"  or point at a manifest: --agent <path/to/avp-conformance.json>"
    )


def preflight(name: str) -> str | None:
    """Return why `name` can't run here, or None if its prerequisites are present.

    An installed agent is a self-contained artifact, so its only prerequisites
    are runtime ones (e.g. the `claude` CLI the Claude agent shells out to). The
    in-repo dev fallback builds from source, so it additionally needs the build
    toolchain. The API key is checked separately by the CLI; every agent needs it.
    """
    if is_installed(name):
        return _installed_preflight(name)
    if name == "goose":
        if shutil.which("cargo") is None:
            return (
                "cargo not on PATH (the in-repo Goose agent builds via cargo; "
                "or run `avp agent install goose` for the prebuilt binary)"
            )
        return None
    if name == "claude-code":
        if importlib.util.find_spec("claude_agent_sdk") is None:
            return (
                "claude-agent-sdk not installed (pip install claude-agent-sdk, "
                "or run `avp agent install claude-code`)"
            )
        if shutil.which("claude") is None:
            return "the `claude` CLI is not on PATH"
        return None
    return None  # custom manifest: trust the caller


def _installed_preflight(name: str) -> str | None:
    """Runtime prerequisites for an already-installed agent."""
    if name == "claude-code" and shutil.which("claude") is None:
        return "the `claude` CLI is not on PATH (the Claude agent shells out to it)"
    return None

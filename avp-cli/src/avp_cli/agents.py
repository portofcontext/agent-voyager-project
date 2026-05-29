"""The agents an eval can run against: Goose and Claude Code.

Each is just its `avp-conformance.json` manifest, the same one the conformance
harness drives. `resolve_agent` accepts a registry name (`goose`,
`claude-code`) or a path to any agent's manifest, so you can point the eval at
a third agent without code changes. `preflight` reports why an agent can't run
locally (missing toolchain / CLI) so the CLI can skip cleanly instead of
producing a board of all-errored runs.
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from pathlib import Path

from avp_conformance.manifest import AgentManifest

from avp_cli.agent import load_manifest

# Manifest path relative to the repo root, per known agent.
_REGISTRY: dict[str, str] = {
    "goose": "agents/avp-goose/rust/avp-conformance.json",
    "claude-code": "agents/avp-claude-agent-sdk/python/avp-conformance.json",
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
    return list(_REGISTRY)


def resolve_agent(spec: str) -> ResolvedAgent:
    """Resolve a registry name or a manifest path to a runnable agent."""
    if spec in _REGISTRY:
        path = _repo_root() / _REGISTRY[spec]
        name = spec
    else:
        path = Path(spec)
        name = path.parent.name or spec
    if not path.is_file():
        raise SystemExit(f"agent manifest not found: {path}")
    manifest, cwd = load_manifest(path)
    return ResolvedAgent(name=name, manifest=manifest, manifest_cwd=cwd)


def preflight(name: str) -> str | None:
    """Return why `name` can't run here, or None if its toolchain is present.

    Only covers agent-binary prerequisites; the API key is checked separately by
    the CLI since every agent needs it.
    """
    if name == "goose":
        if shutil.which("cargo") is None:
            return "cargo not on PATH (the Goose agent is a Rust binary built via cargo)"
        return None
    if name == "claude-code":
        if importlib.util.find_spec("claude_agent_sdk") is None:
            return "claude-agent-sdk not installed (pip install claude-agent-sdk)"
        if shutil.which("claude") is None:
            return "the `claude` CLI is not on PATH"
        return None
    return None  # custom manifest: trust the caller

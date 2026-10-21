"""Read a built-in agent's package: its version and its release metadata.

Each agent declares how it installs and runs in a sandbox in its own package
file, next to its version and dependencies:

- Python: `[tool.avp.release]` in pyproject.toml (`module`, `wheels` as dist
  names, optional `setup` and `env`)
- Node: `"avp"` in package.json (`node`, `asset`, `entry`, optional `setup`);
  the minimum Node comes from `engines.node`
- Rust: `[package.metadata.avp]` in Cargo.toml (`binary`, `asset`, optional
  `gpu_asset`, `setup`, `gpu_setup`)

Shared by release-manifest.py, agent-pins.py, and test-fresh-installs.py.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "avp-cli" / "src" / "avp_cli" / "agents.json"


@dataclass(frozen=True)
class Package:
    agent: str
    kind: str  # "binary" | "python" | "node"
    path: Path
    version: str
    meta: dict  # the package's avp release metadata
    engines_node: str | None = None


def registry() -> dict[str, dict]:
    return json.loads(REGISTRY.read_text())


def read(agent: str) -> Package:
    """The package of the registered agent `agent`."""
    path = ROOT / registry()[agent]["path"]
    if (path / "pyproject.toml").is_file():
        data = tomllib.loads((path / "pyproject.toml").read_text())
        meta = data["tool"]["avp"]["release"]
        return Package(agent, "python", path, data["project"]["version"], meta)
    if (path / "package.json").is_file():
        data = json.loads((path / "package.json").read_text())
        floor = re.fullmatch(r">=\s*(\d+\.\d+\.\d+)", data.get("engines", {}).get("node", ""))
        return Package(
            agent,
            "node",
            path,
            data["version"],
            data["avp"],
            floor.group(1) if floor else None,
        )
    data = tomllib.loads((path / "Cargo.toml").read_text())
    meta = data["package"]["metadata"]["avp"]
    return Package(agent, "binary", path, data["package"]["version"], meta)

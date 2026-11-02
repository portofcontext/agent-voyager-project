"""An agent release's manifest, `avp-release.json`: how to install and run it.

Every built-in agent release carries one next to its artifacts, and so does a
local build from `make build-agents`. It is written when the release is built,
from the agent's own package metadata, so everything the agent runs with (its
locked Python dependencies, the Node runtime, a CLI it drives) is chosen by the
agent and travels with the release that was tested with it. The CLI keeps no
per-agent install knowledge: `container_recipe` turns any manifest into the
steps that put the agent in a sandbox image.

    {
      "schema_version": 1,
      "agent": "opencode",
      "version": "0.1.2",
      "kind": "node",
      "setup": ["<RUN step>", ...],
      "env": {"NAME": "value"},
      "node": {"version": "22.23.3", "min": "22.19.0",
               "asset": "avp-opencode-{platform}.tar.gz", "entry": "dist/src/main.js"}
    }

`kind` is `binary`, `python`, or `node`, and the matching block says what the
artifacts are. Asset names may contain `{target}` (a Rust target triple,
`x86_64-unknown-linux-gnu`) or `{platform}` (`linux-x64`), filled in for the
machine that installs them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from avp_cli.images import ContainerRecipe

FILENAME = "avp-release.json"
SCHEMA_VERSION = 1

# Where a local build's artifacts are copied in the image.
_STAGE = "/opt/avp-artifacts"
# The image's own `{target}` and `{platform}`, resolved when the image builds.
_IMAGE_TARGET = "$(uname -m)-unknown-linux-gnu"
_IMAGE_PLATFORM = "linux-$(uname -m | sed -e s/x86_64/x64/ -e s/aarch64/arm64/)"
_CURL = (
    "apt-get update && apt-get install -y --no-install-recommends "
    "curl ca-certificates && rm -rf /var/lib/apt/lists/*"
)


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Binary(_Block):
    name: str
    asset: str
    gpu_asset: str | None = None
    gpu_setup: list[str] = []


class Python(_Block):
    module: str
    wheels: list[str]
    requirements: str


class Node(_Block):
    version: str
    min: str
    asset: str
    entry: str


class ReleaseManifest(_Block):
    schema_version: Literal[1]
    agent: str
    version: str
    kind: Literal["binary", "python", "node"]
    setup: list[str] = []
    env: dict[str, str] = {}
    binary: Binary | None = None
    python: Python | None = None
    node: Node | None = None

    @model_validator(mode="after")
    def _kind_block(self) -> ReleaseManifest:
        if getattr(self, self.kind) is None:
            raise ValueError(f"a {self.kind} release needs a `{self.kind}` block")
        return self

    def assets(self, *, target: str, platform: str) -> list[str]:
        """The artifact files a machine with this target and platform installs."""
        if self.binary is not None:
            return [self.binary.asset.format(target=target)]
        if self.python is not None:
            return [*self.python.wheels, self.python.requirements]
        assert self.node is not None
        return [self.node.asset.format(platform=platform)]


class ManifestError(Exception):
    """A release manifest is missing or invalid."""


def load(path: Path) -> ReleaseManifest:
    try:
        return ReleaseManifest.model_validate(json.loads(path.read_text()))
    except FileNotFoundError as exc:
        raise ManifestError(f"no {FILENAME} at {path.parent}") from exc
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ManifestError(f"{path} is not a valid {FILENAME}: {exc}") from exc


def container_recipe(
    m: ReleaseManifest,
    *,
    url: str | None = None,
    artifacts: Path | None = None,
    gpu: bool = False,
) -> ContainerRecipe:
    """The sandbox image recipe for the release `m` describes, with its
    artifacts downloaded from `url` (a published release) or copied in from
    the `artifacts` directory (a local build). Exactly one must be given.

    The agent's setup steps run first, then the artifacts install. `gpu`
    selects a binary release's GPU variant when it has one."""
    if (url is None) == (artifacts is None):
        raise ValueError("pass exactly one of url or artifacts")
    base = url.rstrip("/") if url is not None else _STAGE

    def fetch(asset: str) -> str:
        """A shell command writing the asset to stdout."""
        return f"curl -fsSL {base}/{asset}" if url is not None else f"cat {base}/{asset}"

    setup: list[str] = []
    install: list[str] = []
    if m.binary is not None:
        b = m.binary
        variant = gpu and b.gpu_asset is not None
        asset = (b.gpu_asset if variant else b.asset).format(target=_IMAGE_TARGET)
        setup = [_CURL, *m.setup, *(b.gpu_setup if variant else [])]
        install = [
            f"{fetch(asset)} | tar -xz -C /usr/local/bin && chmod +x /usr/local/bin/{b.name}"
        ]
        command = (b.name,)
    elif m.python is not None:
        p = m.python
        setup = list(m.setup)
        wheels = " ".join(f"{base}/{w}" for w in p.wheels)
        install = [
            f"pip install --no-cache-dir --require-hashes -r {base}/{p.requirements}",
            f"pip install --no-cache-dir --no-deps {wheels}",
        ]
        command = ("python", "-m", p.module)
    else:
        n = m.node
        assert n is not None
        arch = "$(uname -m | sed -e s/x86_64/x64/ -e s/aarch64/arm64/)"
        setup = [
            _CURL,
            *m.setup,
            f"curl -fsSL https://nodejs.org/dist/v{n.version}/node-v{n.version}-linux-{arch}.tar.gz "
            "| tar -xz -C /usr/local --strip-components=1",
        ]
        asset = n.asset.format(platform=_IMAGE_PLATFORM)
        install = [f"mkdir -p /opt/{m.agent} && {fetch(asset)} | tar -xz -C /opt/{m.agent}"]
        command = ("node", f"/opt/{m.agent}/{n.entry}")
    return ContainerRecipe(
        setup=tuple(setup),
        copy=((".", _STAGE),) if artifacts is not None else (),
        install=tuple(install),
        command=command,
        env=tuple(m.env.items()),
        context=str(artifacts) if artifacts is not None else None,
    )

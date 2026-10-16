"""The agents an eval can run against: the in-tree agents and any manifest.

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
binary, a Python wheel set, or a Node package archive) and where its dev-fallback manifest lives; the
installer (`avp_cli.agent_install`) consumes it. `preflight` reports why an
agent can't run *on the host* (the `describe` path); actual runs happen inside
a sandbox, where `container_recipe` supplies the Linux install + run recipe
(from the manifest's `container` block, or built in here for known agents).
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from avp_cli import paths
from avp_cli.agent import load_manifest
from avp_cli.agent_manifest import AgentManifest
from avp_cli.images import ContainerRecipe


@dataclass(frozen=True)
class AgentSource:
    """How a known agent is distributed and how the CLI installs / falls back to it.

    `kind` selects the install mechanism: `"binary"` (a prebuilt executable
    extracted to `bin/`), `"python"` (a wheel set installed into a managed
    `venv/`), or `"node"` (a self-contained package archive extracted to `app/`
    and run with the host's `node`). `tag_prefix` is the GitHub release tag stem (`agent-goose` →
    `agent-goose-v0.0.1`). `dev_manifest` is the in-repo manifest used only from
    a source checkout.
    """

    name: str
    kind: str  # "binary" | "python" | "node"
    tag_prefix: str
    dev_manifest: str
    # The agent's self-declared `descriptor.agent_name` (what its `describe`
    # reports). Carried as registry metadata so known agents resolve their
    # public identity without spawning a describe.
    descriptor_name: str = ""
    # The release version whose Linux artifacts the container recipe installs.
    # Pinned so the derived image is content-addressed; bump with releases.
    container_version: str = ""
    # binary agents
    binary_name: str | None = None
    # python agents: `python -m <module>`, install `dist` (pulls third-party
    # deps from PyPI), with `wheel_dists` the unpublished in-repo wheels shipped
    # on the release (resolved via --find-links so PyPI's unrelated `avp` isn't).
    # `container_setup` / `container_env` are what the runtime needs in the
    # sandbox besides its wheels (a CLI it shells out to, say).
    module: str | None = None
    dist: str | None = None
    wheel_dists: tuple[str, ...] = field(default_factory=tuple)
    container_setup: tuple[str, ...] = ()
    container_env: tuple[tuple[str, str], ...] = ()
    # node agents: the release asset and the entry script inside it, run as
    # `node <entry>`. An asset containing `{platform}` is one archive per
    # platform (`linux-arm64`, `darwin-x64`, ...) for agents that ship a native
    # binary. `container_setup` also applies (extra packages the agent needs).
    package_asset: str | None = None
    entry: str | None = None


AGENT_SOURCES: dict[str, AgentSource] = {
    "goose": AgentSource(
        name="goose",
        kind="binary",
        descriptor_name="goose",
        tag_prefix="agent-goose",
        dev_manifest="agents/avp-goose/rust/avp-conformance.json",
        # 0.1.0: per-agent Commission allowlist maps + agent_versions pins;
        # hermetic describe (pre-flight skills are build-intrinsic only,
        # builtin:// sources; no host home discovery).
        # 0.1.1: goose `local-inference` + `telemetry` features compiled in, so
        # the `local` provider (in-process llama.cpp + GGUF from Hugging Face) is
        # available alongside the hosted providers.
        # 0.1.2: also publishes a Linux `-vulkan-` binary variant (goose's `vulkan`
        # feature) for the libkrun GPU runtime; the CPU binary is unchanged.
        # 0.1.3: assistant_message.duration_ms reports real inference wall-time
        # (was ~0 because the coalesced turn opened and drained at flush).
        container_version="0.1.3",
        binary_name="avp-goose-conformance",
    ),
    "claude-code": AgentSource(
        name="claude-code",
        kind="python",
        descriptor_name="avp-claude-agent-sdk",
        tag_prefix="agent-claude-code",
        dev_manifest="agents/avp-claude-agent-sdk/python/avp-conformance.json",
        # 0.1.0: per-agent Commission allowlist maps + agent_versions pins;
        # hermetic describe probe (scrubbed HOME, build-intrinsic surface).
        # 0.1.1: subagent pairing state is run-scoped, so an async `Agent`
        # dispatch whose notification lands turns later still closes its frame;
        # a child still in flight at run end closes as `abandoned` and the run
        # stops as `abandoned` rather than reporting `converged`.
        container_version="0.1.1",
        module="avp_claude_agent_sdk.conformance",
        dist="avp-claude-agent-sdk",
        # The conformance entrypoint also imports avp_conformance (load_commission
        # / load_built_in), which pulls the wire types + typer; ship all the
        # in-repo wheels. `agent-voyager-project` is the renamed `avp` dist.
        wheel_dists=("agent-voyager-project", "avp-conformance", "avp-claude-agent-sdk"),
        # The SDK shells out to the `claude` CLI, which refuses bypassPermissions
        # as root (the container's default user) unless it's told it is already
        # inside a sandbox. It is.
        container_setup=(
            "apt-get update && apt-get install -y --no-install-recommends "
            "nodejs npm ca-certificates && rm -rf /var/lib/apt/lists/*",
            "npm install -g @anthropic-ai/claude-code",
        ),
        container_env=(("IS_SANDBOX", "1"),),
    ),
    "codex": AgentSource(
        name="codex",
        kind="python",
        descriptor_name="avp-codex",
        tag_prefix="agent-codex",
        dev_manifest="agents/avp-codex/python/avp-conformance.json",
        # 0.0.1: the official Codex Python SDK (openai-codex 0.162.1), whose
        # platform wheel bundles the Codex runtime; nothing else to install.
        container_version="0.0.1",
        module="avp_codex.conformance",
        dist="avp-codex",
        wheel_dists=("agent-voyager-project", "avp-codex"),
    ),
    "openai-agents": AgentSource(
        name="openai-agents",
        kind="python",
        descriptor_name="avp-openai-agents",
        tag_prefix="agent-openai-agents",
        dev_manifest="agents/avp-openai-agents/python/avp-conformance.json",
        # 0.0.1: the OpenAI Agents SDK, tools from Commission MCP servers only.
        container_version="0.0.1",
        module="avp_openai_agents.conformance",
        dist="avp-openai-agents",
        wheel_dists=("agent-voyager-project", "avp-openai-agents"),
    ),
    "pi": AgentSource(
        name="pi",
        kind="node",
        descriptor_name="avp-pi",
        tag_prefix="agent-pi",
        dev_manifest="agents/avp-pi/typescript/avp-conformance.json",
        # 0.1.0: Pi coding agent 1.2.0 on the TypeScript Recorder; Commission
        # MCP servers through Pi's MCP extension.
        container_version="0.1.0",
        package_asset="avp-pi.tar.gz",
        entry="dist/src/main.js",
    ),
    "gemini-cli": AgentSource(
        name="gemini-cli",
        kind="node",
        descriptor_name="avp-gemini-cli",
        tag_prefix="agent-gemini-cli",
        dev_manifest="agents/avp-gemini-cli/typescript/avp-conformance.json",
        # 0.1.0: Gemini CLI core 0.63.0 (its headless session) on the
        # TypeScript Recorder; Commission MCP servers through its MCP client.
        container_version="0.1.0",
        package_asset="avp-gemini-cli.tar.gz",
        entry="dist/src/main.js",
    ),
    "deep-agents": AgentSource(
        name="deep-agents",
        kind="python",
        descriptor_name="avp-deep-agents",
        tag_prefix="agent-deep-agents",
        dev_manifest="agents/avp-deep-agents/python/avp-conformance.json",
        # 0.1.0: LangChain Deep Agents 0.7.25 on a workspace filesystem + shell
        # backend; OpenAI, Anthropic, and Google models; recorded through the reusable
        # LangChain callback handler.
        container_version="0.1.0",
        module="avp_deep_agents.conformance",
        dist="avp-deep-agents",
        wheel_dists=("agent-voyager-project", "avp-deep-agents"),
    ),
    "opencode": AgentSource(
        name="opencode",
        kind="node",
        descriptor_name="avp-opencode",
        tag_prefix="agent-opencode",
        dev_manifest="agents/avp-opencode/typescript/avp-conformance.json",
        # 0.1.0: OpenCode 1.18.34 (`opencode serve` per run) on the TypeScript
        # Recorder. Its grep and glob tools use ripgrep.
        container_version="0.1.0",
        package_asset="avp-opencode-{platform}.tar.gz",
        entry="dist/src/main.js",
        container_setup=(
            "apt-get update && apt-get install -y --no-install-recommends ripgrep "
            "&& rm -rf /var/lib/apt/lists/*",
        ),
    ),
}

# The in-repo library wheels every Python agent release ships next to its own
# (the wire types and the conformance harness), versioned in lockstep.
_LIBRARY_WHEEL_VERSION = "0.1.1"

# Node agents need at least this runtime (Pi's own `engines` floor); the
# container recipe installs the pinned NODE_VERSION.
NODE_MIN = (22, 19, 0)
NODE_VERSION = "22.23.3"

_RELEASE_DL = "https://github.com/portofcontext/agent-voyager-project/releases/download"


def _builtin_recipe(source: AgentSource, *, gpu: bool = False) -> ContainerRecipe:
    """The container recipe for an in-tree agent, pinned to `container_version`.

    Install steps run at image-build time (full network); `$(uname -m)` picks
    the asset for the image's arch (aarch64 on Apple Silicon, x86_64 on amd64),
    matching the release's `-unknown-linux-gnu` artifact names.

    `gpu` selects the Linux `-vulkan-` binary variant and installs the Vulkan
    loader + Mesa's Venus ICD, so the agent's local model offloads to a GPU the
    runtime exposes (the libkrun backend's virtio-gpu Venus device). Only the
    binary kind ships a Vulkan variant.
    """
    tag = f"{source.tag_prefix}-v{source.container_version}"
    if source.kind == "binary":
        variant = "vulkan-" if gpu else ""
        asset = f"{source.binary_name}-{variant}$(uname -m)-unknown-linux-gnu.tar.gz"
        # libgomp1: goose's `local-inference` build links llama.cpp with OpenMP
        # (libgomp.so.1), which the slim base lacks; without it the binary fails
        # to start. The GPU variant also needs libvulkan1 + the Venus ICD
        # (mesa-vulkan-drivers) to reach a virtio-gpu device at runtime.
        gpu_pkgs = " libvulkan1 mesa-vulkan-drivers" if gpu else ""
        return ContainerRecipe(
            install=(
                "apt-get update && apt-get install -y --no-install-recommends "
                f"curl ca-certificates libgomp1{gpu_pkgs} && rm -rf /var/lib/apt/lists/*",
                f"curl -fsSL {_RELEASE_DL}/{tag}/{asset} | tar -xz -C /usr/local/bin "
                f"&& chmod +x /usr/local/bin/{source.binary_name}",
            ),
            command=(source.binary_name or source.name,),
        )
    if source.kind == "node":
        # Official Node build for the image's arch (x64 / arm64), then the
        # agent's self-contained archive. Nothing else comes from npm.
        node = f"https://nodejs.org/dist/v{NODE_VERSION}"
        arch = "$(uname -m | sed -e s/x86_64/x64/ -e s/aarch64/arm64/)"
        asset = (source.package_asset or "").replace("{platform}", f"linux-{arch}")
        return ContainerRecipe(
            install=(
                "apt-get update && apt-get install -y --no-install-recommends "
                "curl ca-certificates && rm -rf /var/lib/apt/lists/*",
                *source.container_setup,
                f"curl -fsSL {node}/node-v{NODE_VERSION}-linux-{arch}.tar.gz "
                "| tar -xz -C /usr/local --strip-components=1",
                f"mkdir -p /opt/{source.name} && curl -fsSL "
                f"{_RELEASE_DL}/{tag}/{asset} | tar -xz -C /opt/{source.name}",
            ),
            command=("node", f"/opt/{source.name}/{source.entry}"),
        )

    # Python agent: the in-repo wheels come off the GitHub release (they are not
    # on PyPI); third-party deps resolve from PyPI at build time. Assumes a
    # python base image (the default env image is one); a wrong base fails
    # loudly in the build log. The agent's own wheel carries its release
    # version; the library wheels carry theirs.
    def wheel(dist: str) -> str:
        version = source.container_version if dist == source.dist else _LIBRARY_WHEEL_VERSION
        return f"{_RELEASE_DL}/{tag}/{dist.replace('-', '_')}-{version}-py3-none-any.whl"

    wheels = " ".join(wheel(d) for d in source.wheel_dists)
    return ContainerRecipe(
        install=(*source.container_setup, f"pip install --no-cache-dir {wheels}"),
        command=("python", "-m", source.module or ""),
        env=source.container_env,
    )


class NoContainerRecipe(Exception):
    """The agent can't run: no `container` block and no built-in recipe."""


def container_recipe(agent: ResolvedAgent, *, gpu: bool = False) -> ContainerRecipe:
    """How `agent` gets into and runs inside a sandbox image.

    A manifest's `container` block wins (third-party agents describe
    themselves); known agents fall back to the built-in pinned recipe. An
    agent with neither cannot run (runs are always sandboxed). `gpu` requests
    the built-in GPU recipe variant (a manifest `container` block is used as-is
    either way; third-party GPU images are the agent's own concern)."""
    spec = agent.manifest.container
    if spec is not None:
        return ContainerRecipe(
            install=tuple(spec.install),
            command=tuple(spec.command),
            env=tuple(spec.env.items()),
        )
    source = AGENT_SOURCES.get(agent.name)
    if source is not None and source.container_version:
        return _builtin_recipe(source, gpu=gpu)
    raise NoContainerRecipe(
        f"agent '{agent.name}' has no container recipe: runs execute in a Linux "
        "sandbox, so its manifest needs a `container` block "
        '({"install": ["<RUN step>", ...], "command": ["<argv>", ...]}).'
    )


DEFAULT_AGENT = "claude-code"


def _repo_root() -> Path:
    # .../avp-cli/src/avp_cli/agents.py -> repo root
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ResolvedAgent:
    """An agent located and loadable. `name` is the resolution handle (registry
    alias, or the manifest's directory for a path spec); `agent_name` is the
    agent's self-declared `descriptor.agent_name`, the ONE public identity that
    keys Commission `enabled_builtin_*` / `agent_versions` maps, eval per-agent
    bindings, and board labels. Known agents carry it as registry metadata;
    for a manifest-path agent it's None until a `describe` resolves it."""

    name: str
    manifest: AgentManifest
    manifest_cwd: Path
    agent_name: str | None = None


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
    descriptor_name = AGENT_SOURCES[name].descriptor_name or None
    installed = installed_manifest_path(name)
    if installed.is_file():
        manifest, cwd = load_manifest(installed)
        return ResolvedAgent(
            name=name, manifest=manifest, manifest_cwd=cwd, agent_name=descriptor_name
        )
    dev = _repo_root() / AGENT_SOURCES[name].dev_manifest
    if dev.is_file():
        manifest, cwd = load_manifest(dev)
        return ResolvedAgent(
            name=name, manifest=manifest, manifest_cwd=cwd, agent_name=descriptor_name
        )
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
    source = AGENT_SOURCES.get(name)
    if source is not None and source.kind == "node":
        if reason := node_problem():
            return reason
        built = _repo_root() / Path(source.dev_manifest).parent / (source.entry or "")
        if not built.is_file():
            return f"the in-repo {name} agent is not built (make {name}-build, or avp agent install {name})"
        return None
    return None  # custom manifest: trust the caller


def node_problem() -> str | None:
    """Why the host's `node` can't run a Node agent, or None."""
    node = shutil.which("node")
    floor = ".".join(map(str, NODE_MIN))
    if node is None:
        return f"`node` is not on PATH (Node {floor} or newer runs this agent)"
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return f"could not run `{node} --version`"
    match = re.match(r"v(\d+)\.(\d+)\.(\d+)", out.strip())
    if match is None or tuple(map(int, match.groups())) < NODE_MIN:
        return f"`node` is {out.strip() or 'unknown'}; this agent needs Node {floor} or newer"
    return None


def _installed_preflight(name: str) -> str | None:
    """Runtime prerequisites for an already-installed agent."""
    if name == "claude-code" and shutil.which("claude") is None:
        return "the `claude` CLI is not on PATH (the Claude agent shells out to it)"
    source = AGENT_SOURCES.get(name)
    if source is not None and source.kind == "node":
        return node_problem()
    return None

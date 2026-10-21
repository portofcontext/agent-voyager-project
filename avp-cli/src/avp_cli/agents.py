"""The agents a run can use: installed agents, plus any manifest path.

An agent is installed under `~/.avp/agents/<name>/` by `avp agent install`, and
its `installed.json` says where its code came from:

- **avp release**: one of the built-in agents in `AGENT_SOURCES`, from a GitHub
  release of the AVP repo (or `AVP_AGENT_REPO`'s fork). Built-in names are
  reserved for these.
- **manifest**: a custom agent, installed by name from its own
  `avp-conformance.json`, which must carry a `container` block.
- **local build**: a built-in agent built from your checkout, installed under
  its own name (`--as`). Its artifacts are copied into the sandbox image.

`resolve_agent` resolves an installed name, or a manifest path for a one-off
unregistered agent. Nothing falls back to the source checkout or to a release
the user did not install. `container_recipe` turns the resolved agent into the
Linux install + run recipe its sandbox image is built from, and `preflight`
reports why an agent can't run *on the host* (the `describe` path).
"""

from __future__ import annotations

import json
import os
import platform
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
    `agent-goose-v0.0.1`). `dev_manifest` is the in-repo manifest the
    conformance harness drives from a source checkout; the CLI never runs it.
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
        # 0.2.0: on the shared Recorder and goose v1.53.0; per-response usage,
        # parallel calls, and background subagents recorded faithfully.
        container_version="0.2.0",
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
        # 0.2.0: on the shared Recorder; final per-response usage (cache inside
        # input, real output counts), no title or probe model calls, and one
        # turn per response with parallel tool calls.
        container_version="0.2.0",
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
        # 0.0.2: the official Codex Python SDK (openai-codex 0.162.1), whose
        # platform wheel bundles the Codex runtime; nothing else to install.
        container_version="0.0.2",
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
        # 0.0.2: the OpenAI Agents SDK, tools from Commission MCP servers only;
        # MCP tool schemas read under MCP SDK 1 or 2.
        container_version="0.0.2",
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
    "pydantic-ai": AgentSource(
        name="pydantic-ai",
        kind="python",
        descriptor_name="avp-pydantic-ai",
        tag_prefix="agent-pydantic-ai",
        dev_manifest="agents/avp-pydantic-ai/python/avp-conformance.json",
        # 0.0.2: Pydantic AI 2.58 on OpenAI, Anthropic, and Google models; tools
        # from Commission MCP servers only, schemas read under MCP SDK 1 or 2.
        container_version="0.0.2",
        module="avp_pydantic_ai.conformance",
        dist="avp-pydantic-ai",
        wheel_dists=("agent-voyager-project", "avp-pydantic-ai"),
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
_LIBRARY_WHEEL_VERSION = "0.2.0"

# Node agents need at least this runtime (Pi's own `engines` floor); the
# container recipe installs the pinned NODE_VERSION.
NODE_MIN = (22, 19, 0)
NODE_VERSION = "22.23.3"

CANONICAL_REPO = "portofcontext/agent-voyager-project"


def release_repo() -> str:
    """The repo built-in agents install from: the canonical one, or a fork."""
    return os.environ.get("AVP_AGENT_REPO", CANONICAL_REPO)


def _release_dl(repo: str) -> str:
    return f"https://github.com/{repo}/releases/download"


def _builtin_recipe(
    source: AgentSource,
    *,
    gpu: bool = False,
    version: str | None = None,
    repo: str | None = None,
    wheels: list[str] | None = None,
) -> ContainerRecipe:
    """The container recipe for a built-in agent's release: `version` (default
    `container_version`, the CLI's pin) from `repo` (default the canonical
    repo). `wheels` are a Python release's wheel asset names, recorded at
    install so the image gets exactly the wheels the host install used.

    Install steps run at image-build time (full network); `$(uname -m)` picks
    the asset for the image's arch (aarch64 on Apple Silicon, x86_64 on amd64),
    matching the release's `-unknown-linux-gnu` artifact names.

    `gpu` selects the Linux `-vulkan-` binary variant and installs the Vulkan
    loader + Mesa's Venus ICD, so the agent's local model offloads to a GPU the
    runtime exposes (the libkrun backend's virtio-gpu Venus device). Only the
    binary kind ships a Vulkan variant.
    """
    version = version or source.container_version
    tag = f"{source.tag_prefix}-v{version}"
    dl = _release_dl(repo or CANONICAL_REPO)
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
                f"curl -fsSL {dl}/{tag}/{asset} | tar -xz -C /usr/local/bin "
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
                f"{dl}/{tag}/{asset} | tar -xz -C /opt/{source.name}",
            ),
            command=("node", f"/opt/{source.name}/{source.entry}"),
        )

    # Python agent: the in-repo wheels come off the GitHub release (they are not
    # on PyPI); third-party deps resolve from PyPI at build time. Assumes a
    # python base image (the default env image is one); a wrong base fails
    # loudly in the build log. The agent's own wheel carries its release
    # version; the library wheels carry theirs.
    def wheel(dist: str) -> str:
        v = version if dist == source.dist else _LIBRARY_WHEEL_VERSION
        return f"{dist.replace('-', '_')}-{v}-py3-none-any.whl"

    names = wheels or [wheel(d) for d in source.wheel_dists]
    urls = " ".join(f"{dl}/{tag}/{name}" for name in names)
    return ContainerRecipe(
        install=(*source.container_setup, f"pip install --no-cache-dir {urls}"),
        command=("python", "-m", source.module or ""),
        env=source.container_env,
    )


def _local_recipe(source: AgentSource, artifacts: Path) -> ContainerRecipe:
    """The container recipe for a local build of a built-in agent: the same
    runtime setup as its release, with the artifacts in `artifacts` copied into
    the image instead of downloaded."""
    names = sorted(p.name for p in artifacts.iterdir())
    stage = "/opt/avp-artifacts"
    copy = ((".", stage),)
    if source.kind == "binary":
        binary = source.binary_name or source.name
        return ContainerRecipe(
            setup=(
                "apt-get update && apt-get install -y --no-install-recommends "
                "ca-certificates libgomp1 && rm -rf /var/lib/apt/lists/*",
            ),
            copy=copy,
            install=(f"install -m 0755 {stage}/{binary} /usr/local/bin/{binary}",),
            command=(binary,),
            context=str(artifacts),
        )
    if source.kind == "node":
        node = f"https://nodejs.org/dist/v{NODE_VERSION}"
        arch = "$(uname -m | sed -e s/x86_64/x64/ -e s/aarch64/arm64/)"
        return ContainerRecipe(
            setup=(
                "apt-get update && apt-get install -y --no-install-recommends "
                "curl ca-certificates && rm -rf /var/lib/apt/lists/*",
                *source.container_setup,
                f"curl -fsSL {node}/node-v{NODE_VERSION}-linux-{arch}.tar.gz "
                "| tar -xz -C /usr/local --strip-components=1",
            ),
            copy=copy,
            install=(
                f"mkdir -p /opt/{source.name} && tar -xzf {stage}/{names[0]} -C /opt/{source.name}",
            ),
            command=("node", f"/opt/{source.name}/{source.entry}"),
            context=str(artifacts),
        )
    wheels = " ".join(f"{stage}/{n}" for n in names)
    return ContainerRecipe(
        setup=source.container_setup,
        copy=copy,
        install=(f"pip install --no-cache-dir {wheels}",),
        command=("python", "-m", source.module or ""),
        env=source.container_env,
        context=str(artifacts),
    )


class NoContainerRecipe(Exception):
    """The agent can't run: no `container` block and no built-in recipe."""


def container_recipe(agent: ResolvedAgent, *, gpu: bool = False) -> ContainerRecipe:
    """How `agent` gets into and runs inside a sandbox image.

    An avp release installs the release its `installed.json` records; a local
    build copies its own artifacts into the image; a manifest agent (installed
    or a one-off path) brings its `container` block. A manifest agent without
    one cannot run, since runs are always sandboxed. `gpu` requests the
    built-in GPU recipe variant; a `container` block is used as-is either way."""
    record = agent.record or {}
    source = AGENT_SOURCES.get(record.get("agent", ""))
    if agent.origin == "release" and source is not None:
        return _builtin_recipe(
            source,
            gpu=gpu,
            version=record.get("version"),
            repo=record.get("repo"),
            wheels=record.get("wheels"),
        )
    if agent.origin == "local" and source is not None:
        return _local_recipe(source, installed_dir(agent.name) / "artifacts")
    spec = agent.manifest.container
    if spec is not None:
        return ContainerRecipe(
            install=tuple(spec.install),
            command=tuple(spec.command),
            env=tuple(spec.env.items()),
        )
    raise NoContainerRecipe(
        f"agent '{agent.name}' has no container recipe: runs execute in a Linux "
        "sandbox, so its manifest needs a `container` block "
        '({"install": ["<RUN step>", ...], "command": ["<argv>", ...]}).'
    )


DEFAULT_AGENT = "claude-code"

# An installed agent's name: also its directory under ~/.avp/agents.
AGENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class ResolvedAgent:
    """An agent located and loadable. `name` is the resolution handle (the
    installed name, or the manifest's directory for a path spec); `agent_name`
    is the agent's self-declared `descriptor.agent_name`, the ONE public
    identity that keys Commission `enabled_builtin_*` / `agent_versions` maps
    and eval per-agent bindings. Built-in agents carry it as registry metadata;
    a manifest agent's is None until a `describe` resolves it.

    `origin` is where the code came from (`release`, `manifest`, `local`, or
    `unregistered` for a one-off manifest path), `origin_label` says so in
    words, and `record` is the install's `installed.json`. `label` names the
    agent on boards when its descriptor name would not tell it apart (a local
    build shares its base agent's descriptor name)."""

    name: str
    manifest: AgentManifest
    manifest_cwd: Path
    agent_name: str | None = None
    origin: str = "unregistered"
    origin_label: str = ""
    record: dict | None = None
    label: str | None = None


def known_agents() -> list[str]:
    """The built-in agent names (reserved; installed from avp releases)."""
    return list(AGENT_SOURCES)


def installed_dir(name: str) -> Path:
    return paths.agents_dir() / name


def installed_record(name: str) -> dict | None:
    """An installed agent's `installed.json`, or None. Records written before
    installs had an origin are read as avp releases (a local install under a
    built-in name has no `--as` name, so it reads as None and asks for one)."""
    if not AGENT_NAME_RE.match(name):
        return None
    p = installed_dir(name) / "installed.json"
    if not p.is_file():
        return None
    try:
        record = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if "from" not in record:
        if record.get("source") != "release" or name not in AGENT_SOURCES:
            return None
        record = {**record, "from": "release", "agent": name, "repo": CANONICAL_REPO}
    return record


def installed_agents() -> list[str]:
    """Every installed agent name: built-in releases, local builds, and custom."""
    root = paths.agents_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if installed_record(p.name) is not None)


def installed_manifest_path(name: str) -> Path:
    """Where an installed agent's generated manifest lives (may not exist)."""
    return installed_dir(name) / "avp-conformance.json"


def is_installed(name: str) -> bool:
    return installed_record(name) is not None


def origin_label(record: dict) -> str:
    """Where an installed agent's code came from, in the words `avp agent list` uses."""
    kind = record.get("from")
    if kind == "release":
        repo = record.get("repo") or CANONICAL_REPO
        fork = f" (fork: {repo})" if repo != CANONICAL_REPO else ""
        return f"avp release {record.get('version', '?')}{fork}"
    if kind == "local":
        return f"local build of {record.get('agent', '?')}"
    return f"manifest {_tilde(Path(record.get('manifest', '?')))}"


def _tilde(p: Path) -> str:
    home = Path.home()
    return f"~/{p.relative_to(home)}" if p.is_relative_to(home) else str(p)


def _not_installed(name: str) -> SystemExit:
    if name in AGENT_SOURCES:
        return SystemExit(
            f"agent '{name}' is not installed.\n"
            f"  install every built-in agent: avp agent install --all\n"
            f"  or just this one:             avp agent install {name}"
        )
    return SystemExit(
        f"no agent named '{name}' (see `avp agent list`).\n"
        f"  install your own:  avp agent install {name} --manifest <path/to/avp-conformance.json>\n"
        f"  or run a manifest: --agent <path/to/avp-conformance.json>"
    )


def resolve_agent(spec: str) -> ResolvedAgent:
    """Resolve an installed agent name, or a manifest path, to a runnable agent."""
    if spec.endswith(".json") or "/" in spec:
        path = Path(spec)
        if not path.is_file():
            raise SystemExit(f"agent manifest not found: {path}")
        manifest, cwd = load_manifest(path)
        return ResolvedAgent(
            name=path.parent.name or spec,
            manifest=manifest,
            manifest_cwd=cwd,
            origin="unregistered",
            origin_label=f"manifest {_tilde(path.resolve())} (not installed)",
        )
    record = installed_record(spec)
    if record is None:
        raise _not_installed(spec)
    kind = record["from"]
    if kind == "manifest":
        path = Path(record.get("manifest", ""))
        if not path.is_file():
            raise SystemExit(
                f"agent '{spec}' is installed from {path}, which no longer exists.\n"
                f"  reinstall it: avp agent install {spec} --manifest <path> --force"
            )
        manifest, cwd = load_manifest(path)
        agent_name = None
    else:
        manifest, cwd = load_manifest(installed_manifest_path(spec))
        agent_name = AGENT_SOURCES[record["agent"]].descriptor_name or None
    return ResolvedAgent(
        name=spec,
        manifest=manifest,
        manifest_cwd=cwd,
        agent_name=agent_name,
        origin=kind,
        origin_label=origin_label(record),
        record=record,
        label=spec if kind == "local" else None,
    )


def preflight(name: str) -> str | None:
    """Return why `name` can't run on the host (`describe`), or None.

    An installed agent is a self-contained artifact, so its only prerequisites
    are runtime ones (e.g. the `claude` CLI the Claude agent shells out to, or
    `node` for a Node agent). A local binary build is a Linux executable, so it
    only describes on a Linux host. Manifest agents are trusted as given; the
    API key is checked separately by the CLI.
    """
    record = installed_record(name)
    if record is None:
        return None if (name.endswith(".json") or "/" in name) else "not installed"
    base = record.get("agent")
    if record["from"] == "manifest" or base not in AGENT_SOURCES:
        return None
    source = AGENT_SOURCES[base]
    if record["from"] == "local" and source.kind == "binary" and platform.system() != "Linux":
        return "a local Linux build; it runs in the sandbox but can't describe on this host"
    if base == "claude-code" and shutil.which("claude") is None:
        return "the `claude` CLI is not on PATH (the Claude agent shells out to it)"
    if source.kind == "node":
        return node_problem()
    return None


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

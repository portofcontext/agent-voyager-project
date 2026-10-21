"""The agents a run can use: installed agents, plus any manifest path.

An agent is installed under `~/.avp/agents/<name>/` by `avp agent install`, and
its `installed.json` says where its code came from:

- **avp release**: one of the built-in agents in `agents.json`, from a GitHub
  release of the AVP repo (or `AVP_AGENT_REPO`'s fork). Built-in names are
  reserved for these.
- **manifest**: a custom agent, installed by name from its own
  `avp-conformance.json`, which must carry a `container` block.
- **local build**: a built-in agent built from your checkout, installed under
  its own name (`--as`). Its artifacts are copied into the sandbox image.

A release and a local build both carry an `avp-release.json`
(`avp_cli.release_manifest`) saying how the agent installs and runs, so the
only thing this module knows about each built-in agent is which release of it
to install.

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
from dataclasses import dataclass
from pathlib import Path

from avp_cli import paths, release_manifest
from avp_cli.agent import load_manifest
from avp_cli.agent_manifest import AgentManifest
from avp_cli.images import ContainerRecipe


@dataclass(frozen=True)
class AgentSource:
    """A built-in agent: its name, the release of it this CLI installs, and
    where its package lives in the AVP repo (`path`). How the agent installs and
    runs comes from that release's own `avp-release.json`, so nothing here
    changes when an agent's runtime does.

    `version` is the release `avp agent install <name>` installs; the registry
    (`agents.json`) is kept equal to each agent's package version by
    `make pins`. `descriptor_name` is the agent's self-declared
    `descriptor.agent_name` (what its `describe` reports), so known agents
    resolve their public identity without spawning a describe.
    """

    name: str
    version: str
    descriptor_name: str
    path: str

    @property
    def tag_prefix(self) -> str:
        """The GitHub release tag stem (`agent-goose` → `agent-goose-v<version>`)."""
        return f"agent-{self.name}"

    @property
    def dev_manifest(self) -> str:
        """The in-repo manifest the conformance harness drives from a checkout."""
        return f"{self.path}/avp-conformance.json"


def _load_sources() -> dict[str, AgentSource]:
    data = json.loads(Path(__file__).with_name("agents.json").read_text())
    return {
        name: AgentSource(name, entry["version"], entry["descriptor"], entry["path"])
        for name, entry in data.items()
    }


AGENT_SOURCES: dict[str, AgentSource] = _load_sources()

CANONICAL_REPO = "portofcontext/agent-voyager-project"


def release_repo() -> str:
    """The repo built-in agents install from: the canonical one, or a fork."""
    return os.environ.get("AVP_AGENT_REPO", CANONICAL_REPO)


def release_url(repo: str, tag: str) -> str:
    """Where a release's assets download from."""
    return f"https://github.com/{repo}/releases/download/{tag}"


class NoContainerRecipe(Exception):
    """The agent can't run: no `container` block and no built-in recipe."""


def installed_release(name: str, record: dict) -> release_manifest.ReleaseManifest:
    """The release manifest a built-in install (a release or a local build) was
    installed from. Installs made before releases carried one have none."""
    d = installed_dir(name)
    path = (d / "artifacts" if record.get("from") == "local" else d) / release_manifest.FILENAME
    try:
        return release_manifest.load(path)
    except release_manifest.ManifestError as exc:
        raise NoContainerRecipe(
            f"agent '{name}' was installed by an older avp-cli and can't run with this one.\n"
            f"  reinstall it: {_reinstall(name, record)}"
        ) from exc


def _reinstall(name: str, record: dict) -> str:
    if record.get("from") == "local":
        return f"avp agent install {record.get('agent')} --as {name} --from <dir> --force"
    return f"avp agent install {name} --force"


def container_recipe(agent: ResolvedAgent, *, gpu: bool = False) -> ContainerRecipe:
    """How `agent` gets into and runs inside a sandbox image.

    An avp release installs its artifacts from the release it was installed
    from, and a local build copies its own into the image, both as the
    release's manifest says. A manifest agent (installed or a one-off path)
    brings its `container` block. A manifest agent without one cannot run,
    since runs are always sandboxed. `gpu` requests a release's GPU variant; a
    `container` block is used as-is either way."""
    record = agent.record or {}
    if agent.origin in ("release", "local") and record.get("agent") in AGENT_SOURCES:
        m = installed_release(agent.name, record)
        if agent.origin == "local":
            return release_manifest.container_recipe(
                m, artifacts=installed_dir(agent.name) / "artifacts", gpu=gpu
            )
        url = release_url(record.get("repo") or CANONICAL_REPO, record.get("tag", ""))
        return release_manifest.container_recipe(m, url=url, gpu=gpu)
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
    `node` for a Node agent). A local build with no artifact for this host (a
    Linux-only binary, say) runs in the sandbox but can't describe here.
    Manifest agents are trusted as given; the API key is checked separately by
    the CLI.
    """
    record = installed_record(name)
    if record is None:
        return None if (name.endswith(".json") or "/" in name) else "not installed"
    base = record.get("agent")
    if record["from"] == "manifest" or base not in AGENT_SOURCES:
        return None
    try:
        m = installed_release(name, record)
    except NoContainerRecipe:
        return f"installed by an older avp-cli; reinstall: {_reinstall(name, record)}"
    if record.get("host") is False:
        return f"no {platform.system()} build installed; it runs in the sandbox but can't describe here"
    if base == "claude-code" and shutil.which("claude") is None:
        return "the `claude` CLI is not on PATH (the Claude agent shells out to it)"
    if m.node is not None:
        return node_problem(m.node.min)
    return None


def node_problem(floor: str) -> str | None:
    """Why the host's `node` can't run a Node agent needing Node `floor`
    (`22.19.0`) or newer, or None."""
    node = shutil.which("node")
    if node is None:
        return f"`node` is not on PATH (Node {floor} or newer runs this agent)"
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return f"could not run `{node} --version`"
    match = re.match(r"v(\d+)\.(\d+)\.(\d+)", out.strip())
    if match is None or tuple(map(int, match.groups())) < tuple(map(int, floor.split("."))):
        return f"`node` is {out.strip() or 'unknown'}; this agent needs Node {floor} or newer"
    return None

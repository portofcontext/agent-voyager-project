"""Install agents into the library at `~/.avp/agents/<name>/`.

Two sources, same result (a self-contained install + a generated manifest the
CLI drives):

- **Release** (`install_release`): download the prebuilt artifacts from a GitHub
  release via the `gh` CLI. Binary agents (goose) get an extracted executable;
  Python agents (claude-code) get a managed `venv/` built from the release's
  wheels. This is the normal path.
- **Local** (`install_local_binary` / `install_local_python`): point the CLI at a
  locally built binary or wheel set, no release needed. This is the contributor
  loop for testing your own agent or a new version before cutting a release
  (`make build-agents` produces the artifacts; see avp-cli/README.md).

Each install writes `avp-conformance.json` (command → the installed artifact,
`cwd: "."` → the install dir) and `installed.json` (provenance). `agents.py`
prefers these over the in-repo dev fallback.

Python agents need `uv` (for the venv); release installs need `gh`. The unpublished
in-repo wheels (e.g. `avp`) ship on the release and are installed by file path, so
PyPI's unrelated `avp` package is never pulled; third-party deps (claude-agent-sdk)
still come from PyPI.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from avp_cli import paths
from avp_cli.agents import AGENT_SOURCES, AgentSource

# Override for forks / testing; defaults to the canonical repo.
RELEASE_REPO = os.environ.get("AVP_AGENT_REPO", "portofcontext/agent-voyager-project")


class InstallError(Exception):
    """An agent could not be installed (bad artifact, missing tool, no release)."""


@dataclass(frozen=True)
class InstallResult:
    name: str
    version: str
    kind: str  # "binary" | "python"
    source: str  # "local" | "release"
    install_dir: Path
    command: list[str]


def current_target() -> str:
    """The Rust target triple for selecting a binary release asset (mac/linux)."""
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
        machine
    )
    if arch is None:
        raise InstallError(f"unsupported architecture {platform.machine()!r}")
    system = platform.system()
    if system == "Darwin":
        return f"{arch}-apple-darwin"
    if system == "Linux":
        return f"{arch}-unknown-linux-gnu"
    raise InstallError(
        f"unsupported platform {system!r} (prebuilt agents + srt are macOS/Linux only)"
    )


def install(
    name: str,
    *,
    version: str | None = None,
    binary: str | Path | None = None,
    wheels: list[str | Path] | None = None,
    force: bool = False,
) -> InstallResult:
    """Install a known agent. With `binary`/`wheels`, install locally; else from a release."""
    source = AGENT_SOURCES.get(name)
    if source is None:
        raise InstallError(f"unknown agent {name!r}; known: {', '.join(AGENT_SOURCES)}")
    if binary is not None:
        if source.kind != "binary":
            raise InstallError(
                f"{name} is a {source.kind} agent; --binary applies to binary agents"
            )
        return install_local_binary(source, binary, force=force)
    if wheels:
        if source.kind != "python":
            raise InstallError(f"{name} is a {source.kind} agent; --wheel applies to python agents")
        return install_local_python(source, wheels, force=force)
    return install_release(source, version=version, force=force)


def install_release(
    source: AgentSource, *, version: str | None = None, force: bool = False
) -> InstallResult:
    """Download a release's artifacts via `gh` and install them."""
    gh = shutil.which("gh")
    if gh is None:
        raise InstallError(
            "remote install needs the GitHub CLI `gh` (https://cli.github.com), "
            "or install from local artifacts with --binary / --wheel"
        )
    tag = f"{source.tag_prefix}-v{version}" if version else _latest_tag(gh, source)
    resolved = tag[len(source.tag_prefix) + 2 :]  # strip "<prefix>-v"
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        if source.kind == "binary":
            target = current_target()
            asset = f"{source.binary_name}-{target}.tar.gz"
            _gh_download(gh, tag, asset, tmpdir)
            binary = _extract_binary(tmpdir / asset, source.binary_name or "", tmpdir)
            return install_local_binary(
                source, binary, version=resolved, force=force, origin="release", target=target
            )
        _gh_download(gh, tag, "*.whl", tmpdir)
        wheels = sorted(tmpdir.glob("*.whl"))
        if not wheels:
            raise InstallError(f"release {tag} carried no .whl assets")
        return install_local_python(
            source, list(wheels), version=resolved, force=force, origin="release"
        )


def install_local_binary(
    source: AgentSource,
    binary: str | Path,
    *,
    version: str = "local",
    force: bool = False,
    origin: str = "local",
    target: str | None = None,
) -> InstallResult:
    """Install a prebuilt binary agent from a local file."""
    binary = Path(binary)
    if not binary.is_file():
        raise InstallError(f"binary not found: {binary}")
    d = _prepare_dir(source.name, force=force)
    dest = d / "bin" / (source.binary_name or binary.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, dest)
    dest.chmod(0o755)
    command = [str(dest)]
    _finalize(d, source, command, version=version, kind="binary", origin=origin, target=target)
    return InstallResult(source.name, version, "binary", origin, d, command)


def install_local_python(
    source: AgentSource,
    wheels: list[str | Path],
    *,
    version: str = "local",
    force: bool = False,
    origin: str = "local",
) -> InstallResult:
    """Install a Python agent into a managed venv from a local wheel set."""
    uv = shutil.which("uv")
    if uv is None:
        raise InstallError(
            "installing a Python agent needs `uv` on PATH (https://docs.astral.sh/uv/)"
        )
    paths_ = [Path(w) for w in wheels]
    missing = [w for w in paths_ if not w.is_file()]
    if missing:
        raise InstallError("wheel(s) not found: " + ", ".join(str(w) for w in missing))

    d = _prepare_dir(source.name, force=force)
    venv = d / "venv"
    _run([uv, "venv", str(venv)], "create the venv")
    py = venv / "bin" / "python"
    # Install the wheels by FILE PATH (not by dist name). This pins `avp` to our
    # in-repo wheel so the index is never consulted for it: there is an unrelated
    # `avp` on PyPI, and resolving by name would let uv pick that (higher-version)
    # package instead. The agent's third-party deps (claude-agent-sdk) still
    # resolve from PyPI normally.
    _run(
        [uv, "pip", "install", "--python", str(py), *[str(w) for w in paths_]],
        "install the agent wheels",
    )
    command = [str(py), "-m", source.module or ""]
    _finalize(d, source, command, version=version, kind="python", origin=origin)
    return InstallResult(source.name, version, "python", origin, d, command)


def uninstall(name: str) -> bool:
    """Remove an installed agent. Returns False if it wasn't installed."""
    d = paths.agents_dir() / name
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


def installed_info(name: str) -> dict | None:
    """The provenance record for an installed agent, or None."""
    p = paths.agents_dir() / name / "installed.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


# ── internals ─────────────────────────────────────────────────────────────────


def _prepare_dir(name: str, *, force: bool) -> Path:
    d = paths.agents_dir() / name
    if d.exists():
        if not force:
            raise InstallError(
                f"agent {name!r} is already installed at {d}; pass --force to reinstall"
            )
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _finalize(
    d: Path,
    source: AgentSource,
    command: list[str],
    *,
    version: str,
    kind: str,
    origin: str,
    target: str | None = None,
) -> None:
    """Write the generated manifest + provenance record."""
    manifest = {
        "command": command,
        "cwd": ".",
        "env": {},
        "description": f"{source.name} ({origin} {kind} agent)",
    }
    (d / "avp-conformance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    record = {
        "name": source.name,
        "version": version,
        "kind": kind,
        "source": origin,
        "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": command,
    }
    if target:
        record["target"] = target
    (d / "installed.json").write_text(json.dumps(record, indent=2) + "\n")


def _latest_tag(gh: str, source: AgentSource) -> str:
    out = _run(
        [gh, "release", "list", "--repo", RELEASE_REPO, "--limit", "100", "--json", "tagName"],
        "list releases",
    )
    tags = [r["tagName"] for r in json.loads(out)]
    prefix = f"{source.tag_prefix}-v"
    matches = [t for t in tags if t.startswith(prefix)]
    if not matches:
        raise InstallError(
            f"no releases for {source.name} (tag prefix {prefix!r}) in {RELEASE_REPO}; "
            "pass --version, or build + install locally with --binary / --wheel"
        )
    return matches[0]  # gh lists newest first


def _gh_download(gh: str, tag: str, pattern: str, dest: Path) -> None:
    _run(
        [
            gh,
            "release",
            "download",
            tag,
            "--repo",
            RELEASE_REPO,
            "--dir",
            str(dest),
            "--pattern",
            pattern,
        ],
        f"download {pattern!r} from {tag}",
    )


def _extract_binary(archive: Path, binary_name: str, dest: Path) -> Path:
    with tarfile.open(archive) as tar:
        tar.extractall(dest)  # trusted: our own release artifact
    for p in dest.rglob(binary_name):
        if p.is_file():
            return p
    raise InstallError(f"{archive.name} did not contain {binary_name!r}")


def _run(cmd: list[str], what: str) -> str:
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise InstallError(f"could not run {cmd[0]!r}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        tail = "\n".join((exc.stderr or exc.stdout or "").strip().splitlines()[-5:])
        raise InstallError(f"failed to {what}:\n{tail or '(no output)'}") from exc
    return result.stdout

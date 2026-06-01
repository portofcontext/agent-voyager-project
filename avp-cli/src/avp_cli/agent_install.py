"""Install agents into the library at `~/.avp/agents/<name>/`.

Two sources, same result (a self-contained install + a generated manifest the
CLI drives):

- **Release** (`install_release`): download the prebuilt artifacts from a GitHub
  release over HTTPS (no `gh`, no auth for a public repo). Binary agents (goose)
  get an extracted executable; Python agents (claude-code) get a managed `venv/`
  built from the release's wheels. This is the normal path.
- **Local** (`install_local_binary` / `install_local_python`): point the CLI at a
  locally built binary or wheel set, no release needed. This is the contributor
  loop for testing your own agent or a new version before cutting a release
  (`make build-agents` produces the artifacts; see avp-cli/README.md).

Each install writes `avp-conformance.json` (command → the installed artifact,
`cwd: "."` → the install dir) and `installed.json` (provenance). `agents.py`
prefers these over the in-repo dev fallback.

Release installs fetch over plain HTTPS (the GitHub REST API + asset URLs via
stdlib urllib): a public repo needs no `gh` and no auth; a `GH_TOKEN` /
`GITHUB_TOKEN` in the environment is used only for private repos or API rate
limits. Python agents additionally need `uv` (for the venv). The unpublished
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
import urllib.error
import urllib.request
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
    """Download a release's artifacts over HTTPS and install them.

    No `gh` and no auth for a public repo: assets are fetched from the GitHub
    REST API + their download URLs via stdlib urllib. A `GH_TOKEN` / `GITHUB_TOKEN`
    in the environment is used if present (private repos, API rate limits).
    """
    tag, resolved, assets = _resolve_release(source, version)
    by_name = {a["name"]: a["browser_download_url"] for a in assets}
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        if source.kind == "binary":
            target = current_target()
            asset = f"{source.binary_name}-{target}.tar.gz"
            url = by_name.get(asset)
            if url is None:
                have = ", ".join(by_name) or "none"
                raise InstallError(f"release {tag} has no asset {asset!r} (assets: {have})")
            archive = tmpdir / asset
            _download(url, archive)
            binary = _extract_binary(archive, source.binary_name or "", tmpdir)
            return install_local_binary(
                source, binary, version=resolved, force=force, origin="release", target=target
            )
        wheels = []
        for name, url in by_name.items():
            if name.endswith(".whl"):
                dest = tmpdir / name
                _download(url, dest)
                wheels.append(dest)
        if not wheels:
            raise InstallError(f"release {tag} carried no .whl assets")
        return install_local_python(source, wheels, version=resolved, force=force, origin="release")


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


def _resolve_release(source: AgentSource, version: str | None) -> tuple[str, str, list[dict]]:
    """Return (tag, version, assets) for the requested (or newest) release."""
    if version:
        tag = f"{source.tag_prefix}-v{version}"
        rel = _api(f"/releases/tags/{tag}")
        return tag, version, rel.get("assets", [])
    prefix = f"{source.tag_prefix}-v"
    for rel in _api("/releases?per_page=100"):  # the API returns newest first
        tag = rel.get("tag_name", "")
        if tag.startswith(prefix):
            return tag, tag[len(prefix) :], rel.get("assets", [])
    raise InstallError(
        f"no releases for {source.name} (tag prefix {prefix!r}) in {RELEASE_REPO}; "
        "pass --version, or build + install locally with --binary / --wheel"
    )


def _auth_headers() -> dict[str, str]:
    headers = {"User-Agent": "avp-cli", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:  # only needed for private repos / API rate limits; public needs none
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _api(path: str):
    url = f"https://api.github.com/repos/{RELEASE_REPO}{path}"
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise InstallError(f"GitHub API {exc.code} ({exc.reason}) for {url}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise InstallError(f"network error reaching GitHub: {exc}") from exc


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as f:
            shutil.copyfileobj(resp, f)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise InstallError(f"failed to download {url}: {exc}") from exc


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

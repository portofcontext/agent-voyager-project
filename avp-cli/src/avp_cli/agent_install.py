"""Install agents into the library at `~/.avp/agents/<name>/`.

Three ways in, recorded in each install's `installed.json` as `from`:

- **avp release** (`install_release`, `install_all`): a built-in agent from a
  GitHub release of the AVP repo over HTTPS (no `gh`, no auth for a public
  repo), at the version this CLI pins unless `--version` says otherwise.
  Binary agents (goose) get an extracted executable; Python agents
  (claude-code) get a managed `venv/` built from the release's wheels; Node
  agents (pi, gemini-cli) get their package archive extracted to `app/`. This
  is the normal path, and `avp agent install --all` installs every one.
- **manifest** (`install_manifest`): a custom agent, installed by name from its
  own `avp-conformance.json`. Built-in names are reserved, and the manifest
  must carry a `container` block because runs are sandboxed.
- **local build** (`install_local_binary` / `install_local_python` /
  `install_local_node`): a built-in agent built from a checkout, installed
  under its own `--as` name. The artifacts are kept in `artifacts/` and copied
  into the sandbox image, so runs use them, and boards show the `--as` name.

Release and local installs write `avp-conformance.json` (command → the
installed artifact, `cwd: "."` → the install dir) for the host-side
`describe`. Release installs fetch over plain HTTPS (the GitHub REST API +
asset URLs via stdlib urllib); a `GH_TOKEN` / `GITHUB_TOKEN` in the
environment is used only for private repos or API rate limits. Python agents
additionally need `uv` (for the venv). The unpublished in-repo wheels (e.g.
`avp`) ship on the release and are installed by file path, so PyPI's
unrelated `avp` package is never pulled; third-party deps (claude-agent-sdk)
still come from PyPI.
"""

from __future__ import annotations

import json
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
from avp_cli.agent import load_manifest
from avp_cli.agents import (
    AGENT_NAME_RE,
    AGENT_SOURCES,
    AgentSource,
    installed_record,
    release_repo,
)


class InstallError(Exception):
    """An agent could not be installed (bad artifact, missing tool, no release)."""


@dataclass(frozen=True)
class InstallResult:
    name: str
    version: str
    kind: str  # "binary" | "python" | "node" | "manifest"
    source: str  # "release" | "local" | "manifest"
    install_dir: Path


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
    raise InstallError(f"unsupported platform {system!r} (prebuilt agents are macOS/Linux only)")


def node_platform() -> str:
    """The `<os>-<arch>` naming a per-platform Node archive (`linux-arm64`, `darwin-x64`)."""
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    if arch is None or system is None:
        raise InstallError(f"no prebuilt archive for {platform.system()} {platform.machine()}")
    return f"{system}-{arch}"


def install(
    name: str,
    *,
    version: str | None = None,
    binary: str | Path | None = None,
    wheels: list[str | Path] | None = None,
    package: str | Path | None = None,
    manifest: str | Path | None = None,
    as_name: str | None = None,
    force: bool = False,
) -> InstallResult:
    """Install a built-in agent's release, a custom agent from `manifest`, or a
    local build of a built-in agent (`binary`/`wheels`/`package` + `as_name`)."""
    _check_name(name)
    local = binary is not None or bool(wheels) or package is not None
    if manifest is not None:
        if name in AGENT_SOURCES:
            raise InstallError(
                f"'{name}' is a built-in agent name.\n"
                f"  install your manifest under another name: "
                f"avp agent install <name> --manifest {manifest}"
            )
        if local or as_name or version:
            raise InstallError("--manifest installs a custom agent as is; drop the other flags")
        return install_manifest(name, manifest, force=force)

    source = AGENT_SOURCES.get(name)
    if source is None:
        raise InstallError(
            f"no built-in agent named '{name}' (built-in: {', '.join(AGENT_SOURCES)}).\n"
            f"  install your own: avp agent install {name} --manifest <path/to/avp-conformance.json>"
        )
    if not local:
        if as_name:
            raise InstallError("--as names a local build; pass --wheel, --binary, or --package")
        return install_release(source, version=version, force=force)

    if not as_name:
        flag = "--binary" if binary else "--package" if package else "--wheel"
        raise InstallError(
            "a local build needs its own name, so it can't be mistaken for the release.\n"
            f"  avp agent install {name} --as {name}-dev {flag} ..."
        )
    _check_name(as_name)
    if as_name in AGENT_SOURCES:
        raise InstallError(f"'{as_name}' is a built-in agent name; pick another --as name")
    if binary is not None:
        if source.kind != "binary":
            raise InstallError(
                f"{name} is a {source.kind} agent; --binary applies to binary agents"
            )
        return install_local_binary(source, binary, install_name=as_name, force=force)
    if wheels:
        if source.kind != "python":
            raise InstallError(f"{name} is a {source.kind} agent; --wheel applies to python agents")
        return install_local_python(source, wheels, install_name=as_name, force=force)
    if source.kind != "node":
        raise InstallError(f"{name} is a {source.kind} agent; --package applies to node agents")
    return install_local_node(source, package, install_name=as_name, force=force)


def install_all(*, force: bool = False):
    """Install every built-in agent's pinned release, continuing past failures.

    Yields `(name, InstallResult | None, error | None)` as each finishes; an
    agent already installed from a release yields `(name, None, None)` unless
    `force`. Never touches custom agents or local builds."""
    for name, source in AGENT_SOURCES.items():
        record = installed_record(name)
        if record is not None and not force:
            yield name, None, None
            continue
        try:
            yield name, install_release(source, force=True), None
        except InstallError as exc:
            yield name, None, str(exc)


def install_release(
    source: AgentSource, *, version: str | None = None, force: bool = False
) -> InstallResult:
    """Download a release's artifacts over HTTPS and install them.

    No `gh` and no auth for a public repo: assets are fetched from the GitHub
    REST API + their download URLs via stdlib urllib. A `GH_TOKEN` / `GITHUB_TOKEN`
    in the environment is used if present (private repos, API rate limits).
    """
    repo = release_repo()
    tag, resolved, assets = _resolve_release(source, version or source.container_version, repo)
    by_name = {a["name"]: a["browser_download_url"] for a in assets}
    record = {"from": "release", "agent": source.name, "repo": repo, "tag": tag}
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
            d = _prepare_dir(source.name, force=force)
            command = [str(_place_binary(d / "bin", binary, source))]
            _finalize(d, source, command, version=resolved, kind="binary", record=record)
            return InstallResult(source.name, resolved, "binary", "release", d)
        if source.kind == "node":
            asset = (source.package_asset or "").replace("{platform}", node_platform())
            url = by_name.get(asset)
            if url is None:
                have = ", ".join(by_name) or "none"
                raise InstallError(f"release {tag} has no asset {asset!r} (assets: {have})")
            archive = tmpdir / asset
            _download(url, archive)
            d = _prepare_dir(source.name, force=force)
            command = _extract_node(d, archive, source)
            _finalize(d, source, command, version=resolved, kind="node", record=record)
            return InstallResult(source.name, resolved, "node", "release", d)
        wheels = []
        for name, url in by_name.items():
            if name.endswith(".whl"):
                dest = tmpdir / name
                _download(url, dest)
                wheels.append(dest)
        if not wheels:
            raise InstallError(f"release {tag} carried no .whl assets")
        d = _prepare_dir(source.name, force=force)
        command = _build_venv(d, wheels, source)
        record["wheels"] = sorted(w.name for w in wheels)
        _finalize(d, source, command, version=resolved, kind="python", record=record)
        return InstallResult(source.name, resolved, "python", "release", d)


def install_manifest(name: str, manifest: str | Path, *, force: bool = False) -> InstallResult:
    """Install a custom agent by name from its manifest, which stays where it
    is (edits to it apply to later runs)."""
    path = Path(manifest).expanduser().resolve()
    if not path.is_file():
        raise InstallError(f"manifest not found: {manifest}")
    try:
        loaded, _ = load_manifest(path)
    except Exception as exc:
        raise InstallError(f"{manifest} is not a valid avp-conformance.json: {exc}") from exc
    if loaded.container is None:
        raise InstallError(
            f"{manifest} has no `container` block.\n"
            "  runs happen in a Linux sandbox, so the manifest must say how to install and "
            'start the agent: {"container": {"install": ["<RUN step>", ...], '
            '"command": ["<argv>", ...]}}'
        )
    d = _prepare_dir(name, force=force)
    _write_record(d, {"name": name, "from": "manifest", "manifest": str(path), "kind": "manifest"})
    return InstallResult(name, "-", "manifest", "manifest", d)


def install_local_binary(
    source: AgentSource, binary: str | Path, *, install_name: str, force: bool = False
) -> InstallResult:
    """Install a local Linux build of a binary agent under `install_name`."""
    binary = Path(binary)
    if not binary.is_file():
        raise InstallError(f"binary not found: {binary}")
    if binary.read_bytes()[:4] != b"\x7fELF":
        raise InstallError(
            f"{binary} is not a Linux binary.\n"
            "  the sandbox runs Linux; build for aarch64-unknown-linux-gnu or "
            "x86_64-unknown-linux-gnu (make build-agents does this)"
        )
    d = _prepare_dir(install_name, force=force)
    command = [str(_place_binary(d / "artifacts", binary, source))]
    _finalize_local(d, source, command, kind="binary", install_name=install_name)
    return InstallResult(install_name, "local", "binary", "local", d)


def install_local_python(
    source: AgentSource,
    wheels: list[str | Path],
    *,
    install_name: str,
    force: bool = False,
) -> InstallResult:
    """Install a local wheel set of a Python agent under `install_name`: a host
    venv for `describe`, and the wheels kept for the sandbox image."""
    paths_ = [Path(w) for w in wheels]
    missing = [w for w in paths_ if not w.is_file()]
    if missing:
        raise InstallError("wheel(s) not found: " + ", ".join(str(w) for w in missing))
    if shutil.which("uv") is None:
        raise InstallError(
            "installing a Python agent needs `uv` on PATH (https://docs.astral.sh/uv/)"
        )
    d = _prepare_dir(install_name, force=force)
    artifacts = d / "artifacts"
    artifacts.mkdir()
    kept = [Path(shutil.copy2(w, artifacts / w.name)) for w in paths_]
    command = _build_venv(d, kept, source)
    _finalize_local(d, source, command, kind="python", install_name=install_name)
    return InstallResult(install_name, "local", "python", "local", d)


def install_local_node(
    source: AgentSource, package: str | Path, *, install_name: str, force: bool = False
) -> InstallResult:
    """Install a local package archive of a Node agent under `install_name`:
    extracted to `app/` for `describe`, and kept for the sandbox image."""
    package = Path(package)
    if not package.is_file():
        raise InstallError(f"package archive not found: {package}")
    d = _prepare_dir(install_name, force=force)
    artifacts = d / "artifacts"
    artifacts.mkdir()
    shutil.copy2(package, artifacts / package.name)
    command = _extract_node(d, package, source)
    _finalize_local(d, source, command, kind="node", install_name=install_name)
    return InstallResult(install_name, "local", "node", "local", d)


def uninstall(name: str) -> bool:
    """Remove an installed agent. Returns False if it wasn't installed."""
    if not AGENT_NAME_RE.match(name):
        return False
    d = paths.agents_dir() / name
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


def installed_info(name: str) -> dict | None:
    """The provenance record for an installed agent, or None."""
    return installed_record(name)


# ── internals ─────────────────────────────────────────────────────────────────


def _check_name(name: str) -> None:
    if not AGENT_NAME_RE.match(name):
        raise InstallError(f"invalid agent name {name!r}: use lowercase letters, digits, '-', '_'")


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


def _place_binary(dest_dir: Path, binary: Path, source: AgentSource) -> Path:
    dest = dest_dir / (source.binary_name or binary.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, dest)
    dest.chmod(0o755)
    return dest


def _build_venv(d: Path, wheels: list[Path], source: AgentSource) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        raise InstallError(
            "installing a Python agent needs `uv` on PATH (https://docs.astral.sh/uv/)"
        )
    venv = d / "venv"
    _run([uv, "venv", str(venv)], "create the venv")
    py = venv / "bin" / "python"
    # Install the wheels by FILE PATH (not by dist name). This pins `avp` to our
    # in-repo wheel so the index is never consulted for it: there is an unrelated
    # `avp` on PyPI, and resolving by name would let uv pick that (higher-version)
    # package instead. The agent's third-party deps (claude-agent-sdk) still
    # resolve from PyPI normally.
    _run(
        [uv, "pip", "install", "--python", str(py), *[str(w) for w in wheels]],
        "install the agent wheels",
    )
    return [str(py), "-m", source.module or ""]


def _extract_node(d: Path, package: Path, source: AgentSource) -> list[str]:
    app = d / "app"
    app.mkdir()
    try:
        with tarfile.open(package) as tar:
            tar.extractall(app, filter="data")
    except (tarfile.TarError, OSError) as exc:
        shutil.rmtree(d)
        raise InstallError(f"could not extract {package.name}: {exc}") from exc
    entry = app / (source.entry or "")
    if not entry.is_file():
        shutil.rmtree(d)
        raise InstallError(f"{package.name} did not contain {source.entry!r}")
    return ["node", str(entry)]


def _write_record(d: Path, record: dict) -> None:
    record = {**record, "installed_at": datetime.now(UTC).isoformat(timespec="seconds")}
    (d / "installed.json").write_text(json.dumps(record, indent=2) + "\n")


def _finalize(
    d: Path,
    source: AgentSource,
    command: list[str],
    *,
    version: str,
    kind: str,
    record: dict,
) -> None:
    """Write the generated host manifest + the release's provenance record."""
    _write_manifest(d, command, f"{source.name} (avp release {version})")
    _write_record(
        d,
        {"name": source.name, **record, "version": version, "kind": kind, "command": command},
    )


def _finalize_local(
    d: Path, source: AgentSource, command: list[str], *, kind: str, install_name: str
) -> None:
    """Write the host manifest + a local build's record, with its artifacts' hashes."""
    import hashlib

    _write_manifest(d, command, f"{install_name} (local build of {source.name})")
    artifacts = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((d / "artifacts").iterdir())
    }
    _write_record(
        d,
        {
            "name": install_name,
            "from": "local",
            "agent": source.name,
            "version": "local",
            "kind": kind,
            "artifacts": artifacts,
            "command": command,
        },
    )


def _write_manifest(d: Path, command: list[str], description: str) -> None:
    manifest = {"command": command, "cwd": ".", "env": {}, "description": description}
    (d / "avp-conformance.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _resolve_release(
    source: AgentSource, version: str | None, repo: str
) -> tuple[str, str, list[dict]]:
    """Return (tag, version, assets) for the requested (or newest) release."""
    if version:
        tag = f"{source.tag_prefix}-v{version}"
        rel = _api(repo, f"/releases/tags/{tag}")
        return tag, version, rel.get("assets", [])
    prefix = f"{source.tag_prefix}-v"
    for rel in _api(repo, "/releases?per_page=100"):  # the API returns newest first
        tag = rel.get("tag_name", "")
        if tag.startswith(prefix):
            return tag, tag[len(prefix) :], rel.get("assets", [])
    raise InstallError(
        f"no releases for {source.name} (tag prefix {prefix!r}) in {repo}; pass --version"
    )


def _auth_headers() -> dict[str, str]:
    import os

    headers = {"User-Agent": "avp-cli", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:  # only needed for private repos / API rate limits; public needs none
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _api(repo: str, path: str):
    url = f"https://api.github.com/repos/{repo}{path}"
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

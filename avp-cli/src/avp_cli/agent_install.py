"""Install agents into the library at `~/.avp/agents/<name>/`.

Three ways in, recorded in each install's `installed.json` as `from`:

- **avp release** (`install_release`, `install_all`): a built-in agent from a
  GitHub release of the AVP repo over HTTPS (no `gh`, no auth for a public
  repo), at the version this CLI pins unless `--version` says otherwise. This
  is the normal path, and `avp agent install --all` installs every one.
- **manifest** (`install_manifest`): a custom agent, installed by name from its
  own `avp-conformance.json`. Built-in names are reserved, and the manifest
  must carry a `container` block because runs are sandboxed.
- **local build** (`install_local`): a built-in agent built from a checkout
  (`make build-agents`), installed under its own `--as` name from a directory
  laid out like a release. The directory is kept in `artifacts/` and copied
  into the sandbox image, so runs use it, and boards show the `--as` name.

A release and a local build both carry an `avp-release.json`
(`avp_cli.release_manifest`) that says what the artifacts are, and the install
follows it: a binary agent gets its executable in `bin/`, a Python agent a
managed `venv/`, a Node agent its package extracted to `app/`. Each install
writes `avp-conformance.json` (command → the installed artifact, `cwd: "."` →
the install dir) for the host-side `describe`.

Release installs fetch over plain HTTPS (the GitHub REST API + asset URLs via
stdlib urllib); a `GH_TOKEN` / `GITHUB_TOKEN` in the environment is used only
for private repos or API rate limits. Python agents additionally need `uv`
(for the venv). Their in-repo wheels (e.g. `avp`) are installed by file path,
so PyPI's unrelated `avp` package is never pulled, and their third-party deps
install at the hash-checked versions in the release's `requirements.txt`, the
same set its sandbox image installs, so an upstream release can't change an
agent after it ships.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from avp_cli import paths, release_manifest
from avp_cli.agent import load_manifest
from avp_cli.agents import (
    AGENT_NAME_RE,
    AGENT_SOURCES,
    AgentSource,
    installed_record,
    release_repo,
)
from avp_cli.release_manifest import ReleaseManifest


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
    from_dir: str | Path | None = None,
    manifest: str | Path | None = None,
    as_name: str | None = None,
    force: bool = False,
) -> InstallResult:
    """Install a built-in agent's release, a custom agent from `manifest`, or a
    local build of a built-in agent (`from_dir` + `as_name`)."""
    _check_name(name)
    if manifest is not None:
        if name in AGENT_SOURCES:
            raise InstallError(
                f"'{name}' is a built-in agent name.\n"
                f"  install your manifest under another name: "
                f"avp agent install <name> --manifest {manifest}"
            )
        if from_dir or as_name or version:
            raise InstallError("--manifest installs a custom agent as is; drop the other flags")
        return install_manifest(name, manifest, force=force)

    source = AGENT_SOURCES.get(name)
    if source is None:
        raise InstallError(
            f"no built-in agent named '{name}' (built-in: {', '.join(AGENT_SOURCES)}).\n"
            f"  install your own: avp agent install {name} --manifest <path/to/avp-conformance.json>"
        )
    if from_dir is None:
        if as_name:
            raise InstallError(
                "--as names a local build; pass --from <dir> (make build-agents writes one)"
            )
        return install_release(source, version=version, force=force)

    if version:
        raise InstallError("--version picks a release; a local build is whatever --from holds")
    if not as_name:
        raise InstallError(
            "a local build needs its own name, so it can't be mistaken for the release.\n"
            f"  avp agent install {name} --as {name}-dev --from {from_dir}"
        )
    _check_name(as_name)
    if as_name in AGENT_SOURCES:
        raise InstallError(f"'{as_name}' is a built-in agent name; pick another --as name")
    return install_local(source, from_dir, install_name=as_name, force=force)


def install_all(*, force: bool = False):
    """Install every built-in agent's pinned release, continuing past failures.

    Yields `(name, InstallResult | None, error | None)` as each finishes; an
    agent already installed at the pinned release yields `(name, None, None)`
    unless `force`, and any other install of it (another version, or one from
    an older avp-cli) is replaced. Never touches custom agents or local builds."""
    for name, source in AGENT_SOURCES.items():
        record = installed_record(name)
        current = (
            record is not None
            and record.get("version") == source.version
            and (paths.agents_dir() / name / release_manifest.FILENAME).is_file()
        )
        if current and not force:
            yield name, None, None
            continue
        try:
            yield name, install_release(source, force=True), None
        except InstallError as exc:
            yield name, None, str(exc)


def install_release(
    source: AgentSource, *, version: str | None = None, force: bool = False
) -> InstallResult:
    """Download a release's manifest and artifacts over HTTPS and install them.

    No `gh` and no auth for a public repo: assets are fetched from the GitHub
    REST API + their download URLs via stdlib urllib. A `GH_TOKEN` / `GITHUB_TOKEN`
    in the environment is used if present (private repos, API rate limits).
    """
    repo = release_repo()
    tag, resolved, assets = _resolve_release(source, version or source.version, repo)
    by_name = {a["name"]: a["browser_download_url"] for a in assets}
    if release_manifest.FILENAME not in by_name:
        raise InstallError(
            f"release {tag} has no {release_manifest.FILENAME}; it predates this avp-cli.\n"
            f"  install the release this CLI pins: avp agent install {source.name}"
        )
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        def fetch(asset: str) -> Path:
            url = by_name.get(asset)
            if url is None:
                have = ", ".join(by_name) or "none"
                raise InstallError(f"release {tag} has no asset {asset!r} (assets: {have})")
            dest = tmpdir / asset
            if not dest.exists():
                _download(url, dest)
            return dest

        m = _load_manifest(fetch(release_manifest.FILENAME), source)
        if m.version != resolved:
            raise InstallError(f"release {tag} describes {source.name} {m.version}, not {resolved}")
        d = _prepare_dir(source.name, force=force)
        try:
            command = _install_host(d, m, fetch, tmpdir)
        except InstallError:
            shutil.rmtree(d, ignore_errors=True)
            raise
        shutil.copy2(fetch(release_manifest.FILENAME), d / release_manifest.FILENAME)
    assert command is not None  # a release's fetch raises rather than skip an asset
    _write_manifest(d, command, f"{source.name} (avp release {resolved})")
    _write_record(
        d,
        {
            "name": source.name,
            "from": "release",
            "agent": source.name,
            "repo": repo,
            "tag": tag,
            "version": resolved,
            "kind": m.kind,
            "command": command,
        },
    )
    return InstallResult(source.name, resolved, m.kind, "release", d)


def install_local(
    source: AgentSource, from_dir: str | Path, *, install_name: str, force: bool = False
) -> InstallResult:
    """Install a local build of a built-in agent under `install_name` from a
    directory laid out like its release (artifacts + `avp-release.json`). The
    directory is kept in `artifacts/` for the sandbox image; the host install
    uses this machine's artifact when the directory has one."""
    src = Path(from_dir).expanduser()
    if not src.is_dir():
        raise InstallError(f"not a directory: {from_dir}")
    m = _load_manifest(src / release_manifest.FILENAME, source)
    d = _prepare_dir(install_name, force=force)
    artifacts = d / "artifacts"
    shutil.copytree(src, artifacts)

    def fetch(asset: str) -> Path | None:
        path = artifacts / asset
        return path if path.is_file() else None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            command = _install_host(d, m, fetch, Path(tmp))
    except InstallError:
        shutil.rmtree(d, ignore_errors=True)
        raise
    _write_manifest(
        d,
        command or ["false"],
        f"{install_name} (local build of {source.name})",
    )
    _write_record(
        d,
        {
            "name": install_name,
            "from": "local",
            "agent": source.name,
            "version": "local",
            "kind": m.kind,
            "host": command is not None,
            "artifacts": {
                p.relative_to(artifacts).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(artifacts.rglob("*"))
                if p.is_file()
            },
            "command": command,
        },
    )
    return InstallResult(install_name, "local", m.kind, "local", d)


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


def _load_manifest(path: Path, source: AgentSource) -> ReleaseManifest:
    try:
        m = release_manifest.load(path)
    except release_manifest.ManifestError as exc:
        raise InstallError(str(exc)) from exc
    if m.agent != source.name:
        raise InstallError(f"{path} describes agent {m.agent!r}, not {source.name!r}")
    return m


def _install_host(
    d: Path, m: ReleaseManifest, fetch: Callable[[str], Path | None], tmpdir: Path
) -> list[str] | None:
    """Install the release `m` describes on this host for `describe`; returns
    the command that runs it, or None when `fetch` has no artifact for this
    machine (a local build holding only Linux builds, say)."""
    if m.binary is not None:
        archive = fetch(m.binary.asset.format(target=current_target()))
        if archive is None:
            return None
        binary = _extract_binary(archive, m.binary.name, tmpdir / "bin")
        dest = d / "bin" / m.binary.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, dest)
        dest.chmod(0o755)
        return [str(dest)]
    if m.python is not None:
        files = [fetch(w) for w in m.python.wheels]
        lock = fetch(m.python.requirements)
        missing = [n for n, p in zip(m.python.wheels, files, strict=True) if p is None]
        if lock is None:
            missing.append(m.python.requirements)
        if missing:
            raise InstallError(f"missing {', '.join(missing)}")
        return _build_venv(d, [p for p in files if p is not None], lock, m.python.module)
    assert m.node is not None
    archive = fetch(m.node.asset.format(platform=node_platform()))
    if archive is None:
        return None
    return _extract_node(d, archive, m.node.entry)


def _build_venv(d: Path, wheels: list[Path], requirements: Path, module: str) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        raise InstallError(
            "installing a Python agent needs `uv` on PATH (https://docs.astral.sh/uv/)"
        )
    venv = d / "venv"
    _run([uv, "venv", str(venv)], "create the venv")
    py = venv / "bin" / "python"
    # Third-party deps first, at the release's locked, hash-checked versions.
    # Then the wheels by FILE PATH (not by dist name) and without resolving:
    # there is an unrelated `avp` on PyPI, and resolving by name could pick it.
    _run(
        [uv, "pip", "install", "--python", str(py), "--require-hashes", "-r", str(requirements)],
        "install the agent's locked dependencies",
    )
    _run(
        [uv, "pip", "install", "--python", str(py), "--no-deps", *[str(w) for w in wheels]],
        "install the agent wheels",
    )
    return [str(py), "-m", module]


def _extract_node(d: Path, package: Path, entry: str) -> list[str]:
    app = d / "app"
    app.mkdir()
    try:
        with tarfile.open(package) as tar:
            tar.extractall(app, filter="data")
    except (tarfile.TarError, OSError) as exc:
        raise InstallError(f"could not extract {package.name}: {exc}") from exc
    if not (app / entry).is_file():
        raise InstallError(f"{package.name} did not contain {entry!r}")
    return ["node", str(app / entry)]


def _write_record(d: Path, record: dict) -> None:
    record = {**record, "installed_at": datetime.now(UTC).isoformat(timespec="seconds")}
    (d / "installed.json").write_text(json.dumps(record, indent=2) + "\n")


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

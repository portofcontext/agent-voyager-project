"""Declarative agent environments (CLI-side; the AVP spec never sees these).

An environment block describes a *user-space* world to run an agent in:

    { "runtimes": ["python@3.12"], "packages": {"pip": ["pandas"]},
      "files": {"config.toml": "k = 1\n", "data.csv": {"from": "fixtures/d.csv"}},
      "setup": ["python -m compileall ."],
      "expose": {"write": ["./out"], "net": ["api.example.com"]} }

`materialize` turns that into two dirs under a run root: a **prefix** (toolchains
+ packages, installed without root) and a **workspace** (seeded with `files`),
plus the launch facts the runner needs (PATH additions, env vars, and the srt
write/network allow-lists from `expose`). The agent then runs with `cwd` = the
workspace and the prefix on `PATH`, so its tool calls (e.g. `python ...`) hit the
provisioned toolchain. Confinement (srt) keeps writes inside the workspace.

Scope: user-space only (pip via uv, later npm/go/rust, plus a `setup` escape
hatch). System packages / a different base OS are the Docker realizer, not this.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Languages the schema accepts. Having a provisioner is a separate question
# (see _PROVISIONERS): the block validates for node/go before we ship them, and
# materialize() is where "not implemented yet" surfaces.
KNOWN_RUNTIMES = ("python", "node", "go", "rust")

_ALLOWED_KEYS = {"runtimes", "packages", "paths", "files", "setup", "expose"}
# Which ecosystem package list feeds each toolchain's provisioner.
_PACKAGE_KEY = {"python": "pip", "node": "npm"}

# Names skipped when a `--path` directory is copied into the workspace, so
# pointing at a real repo doesn't drag in VCS metadata, deps, or build caches.
_COPY_IGNORE = (
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "*.pyc",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
)


class EnvError(Exception):
    """An environment block is malformed or asks for something unsupported."""


def parse_runtime(spec: str) -> tuple[str, str | None]:
    """`'python@3.12'` -> `('python', '3.12')`; `'python'` -> `('python', None)`."""
    lang, _, version = spec.partition("@")
    if lang not in KNOWN_RUNTIMES:
        raise EnvError(f"unsupported runtime {lang!r}; known: {', '.join(KNOWN_RUNTIMES)}")
    return lang, (version or None)


@dataclass(frozen=True)
class Expose:
    write: list[str] = field(default_factory=list)
    net: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Environment:
    runtimes: list[str] = field(default_factory=list)
    packages: dict[str, list[str]] = field(default_factory=dict)
    paths: list[str] = field(default_factory=list)  # local dirs/files copied into the workspace
    files: dict[str, Any] = field(default_factory=dict)  # path -> str | {"from": path}
    setup: list[str] = field(default_factory=list)
    expose: Expose = field(default_factory=Expose)

    @classmethod
    def parse(cls, d: Any) -> Environment:
        if not isinstance(d, dict):
            raise EnvError("environment must be a JSON object")
        unknown = set(d) - _ALLOWED_KEYS
        if unknown:
            raise EnvError(f"unknown environment key(s): {', '.join(sorted(unknown))}")
        exp = d.get("expose") or {}
        if not isinstance(exp, dict):
            raise EnvError("'expose' must be an object")
        return cls(
            runtimes=list(d.get("runtimes") or []),
            packages=dict(d.get("packages") or {}),
            paths=list(d.get("paths") or []),
            files=dict(d.get("files") or {}),
            setup=list(d.get("setup") or []),
            expose=Expose(write=list(exp.get("write") or []), net=list(exp.get("net") or [])),
        )


@dataclass
class Materialized:
    """The realized environment + the facts the runner needs to launch into it."""

    prefix: Path
    workspace: Path
    path_additions: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    write_paths: list[str] = field(default_factory=list)
    net: list[str] = field(default_factory=list)


def _copy_paths(paths: list[str], workspace: Path, *, base_dir: Path) -> None:
    """Copy each local dir/file in `paths` into the workspace (fresh each run).

    A directory's *contents* land at the workspace root (tree preserved); a file
    lands at the workspace root by name. Relative entries resolve against
    `base_dir`. VCS metadata, dep dirs, and build caches (`_COPY_IGNORE`) are
    skipped so pointing at a real repo stays lean. This is how you point an env
    at a real codebase to curate."""
    ignore = shutil.ignore_patterns(*_COPY_IGNORE)
    for p in paths:
        src = Path(p)
        if not src.is_absolute():
            src = base_dir / p
        src = src.resolve()
        if not src.exists():
            raise EnvError(f"path source not found: {p}")
        if src.is_dir():
            shutil.copytree(src, workspace, dirs_exist_ok=True, ignore=ignore)
        else:
            shutil.copy2(src, workspace / src.name)


def seed_files(files: dict[str, Any], workspace: Path, *, base_dir: Path) -> None:
    """Write `files` into `workspace`: inline strings, or `{from: localpath}` copies.

    Paths are confined to the workspace (no `..` escape). `{from}` is resolved
    relative to `base_dir` (the env file's directory)."""
    ws = workspace.resolve()
    for rel, spec in files.items():
        dest = (workspace / rel).resolve()
        if not dest.is_relative_to(ws):
            raise EnvError(f"file path {rel!r} escapes the workspace")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(spec, str):
            dest.write_text(spec)
        elif isinstance(spec, dict) and "from" in spec:
            src = (base_dir / spec["from"]).resolve()
            if not src.is_file():
                raise EnvError(f"file source not found: {spec['from']}")
            shutil.copy2(src, dest)
        else:
            raise EnvError(f"file {rel!r} must be a string or {{'from': path}}")


def materialize(env: Environment, root: Path, *, base_dir: Path) -> Materialized:
    """Build the env's prefix + workspace and return the launch facts.

    Provisions each toolchain into the prefix, runs `setup`, seeds `files` into
    the workspace, and folds `expose` into the write / network allow-lists. The
    workspace is always writable; everything else stays read-only under srt.
    """
    prefix = root / "prefix"
    workspace = root / "workspace"
    prefix.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    mat = Materialized(prefix=prefix, workspace=workspace)

    for spec in env.runtimes:
        lang, version = parse_runtime(spec)
        provision = _PROVISIONERS.get(lang)
        if provision is None:
            raise EnvError(
                f"{lang} provisioning is not implemented yet; install it via the "
                "'setup' commands for now"
            )
        provision(prefix, version, env.packages.get(_PACKAGE_KEY.get(lang, lang), []), mat)

    if env.setup:
        run_env = {**os.environ, **mat.env_vars}
        if mat.path_additions:
            run_env["PATH"] = os.pathsep.join([*mat.path_additions, run_env.get("PATH", "")])
        for command in env.setup:
            _run(["bash", "-lc", command], f"setup: {command}", cwd=workspace, env=run_env)

    _copy_paths(env.paths, workspace, base_dir=base_dir)
    seed_files(env.files, workspace, base_dir=base_dir)  # inline files layer on top of copied trees

    mat.write_paths = [str(workspace), *(_abs(base_dir, p) for p in env.expose.write)]
    mat.net = list(env.expose.net)
    return mat


def parse_file_arg(s: str) -> tuple[str, Any]:
    """`'a.py=code'` -> `('a.py', 'code')`; `'d.csv=@local'` -> `('d.csv', {'from': 'local'})`."""
    path, sep, value = s.partition("=")
    if not sep or not path:
        raise EnvError(f"--file must be PATH=CONTENT or PATH=@localfile, got {s!r}")
    return path, ({"from": value[1:]} if value.startswith("@") else value)


def build_block(
    *,
    runtimes: tuple[str, ...] = (),
    pip: tuple[str, ...] = (),
    npm: tuple[str, ...] = (),
    paths: tuple[str, ...] = (),
    files: tuple[str, ...] = (),
    setup: tuple[str, ...] = (),
    write: tuple[str, ...] = (),
    net: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Assemble an environment block from `avp env create` flags, validated.

    Runtimes are `LANG@VERSION` (or bare `LANG`), one uniform form for every
    language. `files` entries are `PATH=CONTENT` or `PATH=@localfile`. Raises
    `EnvError` on an unsupported runtime or a malformed `--file`."""
    block: dict[str, Any] = {}
    for t in runtimes:
        parse_runtime(t)  # validate the runtime name up front
    if runtimes:
        block["runtimes"] = list(runtimes)
    packages: dict[str, list[str]] = {}
    if pip:
        packages["pip"] = list(pip)
    if npm:
        packages["npm"] = list(npm)
    if packages:
        block["packages"] = packages
    if paths:
        block["paths"] = list(paths)
    if files:
        block["files"] = dict(parse_file_arg(f) for f in files)
    if setup:
        block["setup"] = list(setup)
    expose: dict[str, list[str]] = {}
    if write:
        expose["write"] = list(write)
    if net:
        expose["net"] = list(net)
    if expose:
        block["expose"] = expose
    Environment.parse(block)  # final shape validation
    return block


def launch_env(command: list[str], mat: Materialized) -> tuple[list[str], Path, dict[str, str]]:
    """Prepare `command` to run inside `mat`: returns (argv, cwd, env).

    `cwd` is the env workspace, the toolchain prefix is prepended to `PATH`, and
    the env's vars (e.g. `VIRTUAL_ENV`) are set. The caller adds any srt wrapping.
    """
    proc_env = dict(os.environ)
    proc_env.update(mat.env_vars)
    if mat.path_additions:
        proc_env["PATH"] = os.pathsep.join([*mat.path_additions, proc_env.get("PATH", "")])
    return command, mat.workspace, proc_env


# ── provisioners (prefix, version, packages, mat) -> None ─────────────────────


def _provision_python(
    prefix: Path, version: str | None, packages: list[str], mat: Materialized
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise EnvError("a python environment needs `uv` on PATH (https://docs.astral.sh/uv/)")
    venv = prefix / "python"
    cmd = [uv, "venv", str(venv)]
    if version:
        cmd += ["--python", version]
    _run(cmd, "create the python environment")
    if packages:
        _run(
            [uv, "pip", "install", "--python", str(venv / "bin" / "python"), *packages],
            "install pip packages",
        )
    mat.path_additions.append(str(venv / "bin"))
    mat.env_vars["VIRTUAL_ENV"] = str(venv)


_PROVISIONERS: dict[str, Callable[[Path, str | None, list[str], Materialized], None]] = {
    "python": _provision_python,
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _abs(base_dir: Path, p: str) -> str:
    return p if os.path.isabs(p) else str(base_dir / p)


def _run(cmd: list[str], what: str, *, cwd: Path | None = None, env: dict | None = None) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd, env=env)
    except FileNotFoundError as exc:
        raise EnvError(f"could not run {cmd[0]!r}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        tail = "\n".join((exc.stderr or exc.stdout or "").strip().splitlines()[-5:])
        raise EnvError(f"failed to {what}:\n{tail or '(no output)'}") from exc

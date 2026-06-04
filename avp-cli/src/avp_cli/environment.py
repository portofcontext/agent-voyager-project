"""Declarative agent environments (CLI-side; the AVP spec never sees these).

An environment block describes the *container world* an agent runs in:

    { "image": "python:3.12-slim",
      "packages": {"apt": ["git"], "pip": ["pandas"]},
      "paths": ["/abs/code/repo"],
      "files": {"config.toml": "k = 1\n", "data.csv": {"from": "fixtures/d.csv"}},
      "setup": ["pip install -e ."],
      "net": ["api.example.com"],
      "resources": {"cpu": "2", "memory": "4Gi"} }

Everything is explicit; nothing comes from the host machine. `image` +
`packages` (+ the agent's container recipe) compile to a derived image, built
and cached by `avp_cli.images`. `paths` and `files` seed a fresh per-run
workspace on the host, which is bind-mounted into the sandbox. `setup` runs
inside the sandbox in the workspace before the agent starts. `net` extends the
default-deny egress allowlist; `resources` caps cpu/memory.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The world an agent gets when no --env is given: a small, current Python base.
DEFAULT_IMAGE = "python:3.12-slim"

_ALLOWED_KEYS = {"image", "packages", "paths", "files", "setup", "net", "resources"}
_PACKAGE_ECOSYSTEMS = ("apt", "pip")
_RESOURCE_KEYS = {"cpu", "memory"}

# The pre-container spec shape; rejected with a pointer to the new model.
_REMOVED_KEYS = {"runtimes", "expose"}

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


@dataclass(frozen=True)
class Environment:
    image: str = DEFAULT_IMAGE
    packages: dict[str, list[str]] = field(default_factory=dict)
    paths: list[str] = field(default_factory=list)  # local dirs/files copied into the workspace
    files: dict[str, Any] = field(default_factory=dict)  # path -> str | {"from": path}
    setup: list[str] = field(default_factory=list)  # run in-sandbox, in the workspace
    net: list[str] = field(default_factory=list)  # extra egress allow-list domains
    resources: dict[str, str] = field(default_factory=dict)  # {"cpu": "2", "memory": "4Gi"}

    @classmethod
    def parse(cls, d: Any) -> Environment:
        if not isinstance(d, dict):
            raise EnvError("environment must be a JSON object")
        removed = set(d) & _REMOVED_KEYS
        if removed:
            raise EnvError(
                f"environment key(s) {', '.join(sorted(removed))} are gone: environments "
                "are container images now. Use 'image' (base image) instead of 'runtimes', "
                "and 'net' instead of 'expose' (writes are contained by the sandbox)."
            )
        unknown = set(d) - _ALLOWED_KEYS
        if unknown:
            raise EnvError(f"unknown environment key(s): {', '.join(sorted(unknown))}")
        packages = dict(d.get("packages") or {})
        bad = set(packages) - set(_PACKAGE_ECOSYSTEMS)
        if bad:
            raise EnvError(
                f"unsupported package ecosystem(s): {', '.join(sorted(bad))}; "
                f"known: {', '.join(_PACKAGE_ECOSYSTEMS)} (anything else: bake it "
                "into the image or use 'setup')"
            )
        resources = dict(d.get("resources") or {})
        bad = set(resources) - _RESOURCE_KEYS
        if bad:
            raise EnvError(
                f"unknown resource key(s): {', '.join(sorted(bad))}; "
                f"known: {', '.join(sorted(_RESOURCE_KEYS))}"
            )
        image = d.get("image") or DEFAULT_IMAGE
        if not isinstance(image, str):
            raise EnvError("'image' must be a string (a container image reference)")
        return cls(
            image=image,
            packages={k: list(v or []) for k, v in packages.items()},
            paths=list(d.get("paths") or []),
            files=dict(d.get("files") or {}),
            setup=list(d.get("setup") or []),
            net=list(d.get("net") or []),
            resources={k: str(v) for k, v in resources.items()},
        )


def seed_workspace(env: Environment, workspace: Path, *, base_dir: Path) -> Path:
    """Build the per-run workspace on the host: copied `paths`, then `files`.

    The workspace is bind-mounted into the sandbox; it is the only host surface
    a run touches. Fresh each run."""
    workspace.mkdir(parents=True, exist_ok=True)
    _copy_paths(env.paths, workspace, base_dir=base_dir)
    seed_files(env.files, workspace, base_dir=base_dir)  # inline files layer on top
    return workspace


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


def parse_file_arg(s: str) -> tuple[str, Any]:
    """`'a.py=code'` -> `('a.py', 'code')`; `'d.csv=@local'` -> `('d.csv', {'from': 'local'})`."""
    path, sep, value = s.partition("=")
    if not sep or not path:
        raise EnvError(f"--file must be PATH=CONTENT or PATH=@localfile, got {s!r}")
    return path, ({"from": value[1:]} if value.startswith("@") else value)


def build_block(
    *,
    image: str | None = None,
    apt: tuple[str, ...] = (),
    pip: tuple[str, ...] = (),
    paths: tuple[str, ...] = (),
    files: tuple[str, ...] = (),
    setup: tuple[str, ...] = (),
    net: tuple[str, ...] = (),
    cpu: str | None = None,
    memory: str | None = None,
) -> dict[str, Any]:
    """Assemble an environment block from `avp env create` flags, validated.

    `files` entries are `PATH=CONTENT` or `PATH=@localfile`. Raises `EnvError`
    on a malformed `--file` or resource value."""
    block: dict[str, Any] = {}
    if image:
        block["image"] = image
    packages: dict[str, list[str]] = {}
    if apt:
        packages["apt"] = list(apt)
    if pip:
        packages["pip"] = list(pip)
    if packages:
        block["packages"] = packages
    if paths:
        block["paths"] = list(paths)
    if files:
        block["files"] = dict(parse_file_arg(f) for f in files)
    if setup:
        block["setup"] = list(setup)
    if net:
        block["net"] = list(net)
    resources: dict[str, str] = {}
    if cpu:
        resources["cpu"] = cpu
    if memory:
        resources["memory"] = memory
    if resources:
        block["resources"] = resources
    Environment.parse(block)  # final shape validation
    return block

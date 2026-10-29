"""Run each released Python agent's tests against a fresh install.

Releases install an agent's dependencies at the workspace lock's versions (its
requirements.txt), so an upstream release can't break an agent that shipped.
This installs the agent's wheels into a clean environment without the lock,
resolving the newest versions the agent allows, adds its dev dependencies,
and runs its tests there. A failure is early warning that refreshing the lock
(`uv lock --upgrade`) would break the agent, say an SDK renaming a field.

Usage: uv run python avp/scripts/test-fresh-installs.py [agent ...]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import agent_packages

ROOT = agent_packages.ROOT
# The Python the sandbox images install agents into.
PYTHON = "3.12"


def _run(cmd: list[str], **kwargs: object) -> None:
    subprocess.run(cmd, check=True, **kwargs)


def check(name: str, work: Path) -> bool:
    pkg = agent_packages.read(name)
    package = pkg.path
    wheels = work / "wheels"
    for dist in pkg.meta["wheels"]:
        _run(
            ["uv", "build", "-q", "--package", dist, "--wheel", "--out-dir", str(wheels)], cwd=ROOT
        )
    venv = work / "venv"
    _run(["uv", "venv", "-q", "--python", PYTHON, str(venv)])
    python = venv / "bin" / "python"
    dev = tomllib.loads((package / "pyproject.toml").read_text())["dependency-groups"]["dev"]
    built = [str(w) for w in sorted(wheels.glob("*.whl"))]
    _run(["uv", "pip", "install", "-q", "--python", str(python), *built, *dev])
    versions = subprocess.run(
        ["uv", "pip", "freeze", "--python", str(python)], capture_output=True, text=True, check=True
    ).stdout
    print(f"==== {name} (fresh install) ====")
    print("  " + ", ".join(line for line in versions.splitlines() if not line.startswith("-")))
    # Run from the package directory so the tests import the installed wheel,
    # not the workspace's editable source.
    result = subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "not real_llm and not docker",
        ],
        cwd=package,
    )
    return result.returncode in (0, 5)


def main(names: list[str]) -> int:
    names = names or [
        n for n in agent_packages.registry() if agent_packages.read(n).kind == "python"
    ]
    failed = []
    for name in names:
        with tempfile.TemporaryDirectory() as tmp:
            if not check(name, Path(tmp)):
                failed.append(name)
    if failed:
        print(f"\nFAILED on fresh installs: {' '.join(failed)}")
        return 1
    print("\nAll agents pass on fresh installs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

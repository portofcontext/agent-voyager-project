"""Run each released Python agent's tests against a fresh install.

`make test` runs agents in the workspace, whose lockfile pins every
dependency. A sandbox image instead pip-installs the agent's wheels, which
resolves the newest versions the agent allows. This installs the same wheels
into a clean environment without the lockfile, adds the agent's dev
dependencies, and runs its tests there, so a dependency that moved upstream
(say, an SDK renaming a field) fails here before it fails in a user's sandbox.

Usage: uv run python avp/scripts/test-fresh-installs.py [agent ...]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from avp_cli.agents import AGENT_SOURCES

ROOT = Path(__file__).resolve().parents[2]
# The Python the sandbox images install agents into.
PYTHON = "3.12"


def _run(cmd: list[str], **kwargs: object) -> None:
    subprocess.run(cmd, check=True, **kwargs)


def check(name: str, work: Path) -> bool:
    source = AGENT_SOURCES[name]
    package = ROOT / Path(source.dev_manifest).parent
    wheels = work / "wheels"
    for dist in source.wheel_dists:
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
    names = names or [n for n, s in AGENT_SOURCES.items() if s.kind == "python"]
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

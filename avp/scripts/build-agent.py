"""Build a built-in agent into a directory laid out like its release.

The directory holds the agent's artifacts and its avp-release.json, so it
installs as a local build (`avp agent install <agent> --as <agent>-dev --from
<dir>`) and smoke-tests (`smoke-agent.py <agent> --from <dir>`) exactly as the
release would. Python agents build their wheels, Node agents run their
package script, and the binary agent builds for this machine (a Linux binary
only on Linux, so on macOS it describes here but can't run in the sandbox).

Usage: uv run python avp/scripts/build-agent.py <agent> <dir>
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import agent_packages

from avp_cli.agent_install import current_target


def build(agent: str, out: Path) -> None:
    pkg = agent_packages.read(agent)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if pkg.kind == "python":
        for dist in pkg.meta["wheels"]:
            subprocess.run(
                ["uv", "build", "-q", "--wheel", "--package", dist, "--out-dir", str(out)],
                cwd=agent_packages.ROOT,
                check=True,
            )
    elif pkg.kind == "node":
        subprocess.run([str(pkg.path / "scripts" / "package.sh"), str(out)], check=True)
    else:
        binary = pkg.meta["binary"]
        subprocess.run(
            ["cargo", "build", "--release", "--features", "conformance", "--bin", binary],
            cwd=pkg.path,
            check=True,
        )
        asset = out / pkg.meta["asset"].format(target=current_target())
        with tarfile.open(asset, "w:gz") as tar:
            tar.add(pkg.path / "target" / "release" / binary, arcname=binary)
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("release-manifest.py")), agent, str(out)],
        check=True,
    )


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    build(sys.argv[1], Path(sys.argv[2]).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())

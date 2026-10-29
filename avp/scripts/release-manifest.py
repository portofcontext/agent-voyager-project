"""Write a built-in agent's avp-release.json into a directory of its artifacts.

The release workflows run this on the artifacts they built, then smoke-test
and publish the directory as is; `make build-agents` runs it for local builds.
The manifest comes from the agent's package metadata (see agent_packages.py).
For a Python agent it also writes requirements.txt: the workspace lock
exported for the agent, hash-checked, without the in-repo wheels.

Usage: uv run python avp/scripts/release-manifest.py <agent> <dir>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import agent_packages

from avp_cli.release_manifest import FILENAME, SCHEMA_VERSION, ReleaseManifest

REQUIREMENTS = "requirements.txt"


def _one(out: Path, pattern: str) -> str:
    found = sorted(p.name for p in out.glob(pattern))
    if len(found) != 1:
        raise SystemExit(f"expected one {pattern} in {out}, found {found or 'none'}")
    return found[0]


def manifest(agent: str, out: Path) -> dict:
    pkg = agent_packages.read(agent)
    meta = pkg.meta
    if meta.get("agent") != agent:
        raise SystemExit(
            f"{pkg.path} declares agent {meta.get('agent')!r}, registered as {agent!r}"
        )
    data: dict = {
        "schema_version": SCHEMA_VERSION,
        "agent": agent,
        "version": pkg.version,
        "kind": pkg.kind,
        "setup": meta.get("setup", []),
        "env": meta.get("env", {}),
    }
    if pkg.kind == "python":
        wheels = [_one(out, f"{dist.replace('-', '_')}-*.whl") for dist in meta["wheels"]]
        dist = meta["wheels"][-1]
        if not wheels[-1].startswith(f"{dist.replace('-', '_')}-{pkg.version}-"):
            raise SystemExit(f"{wheels[-1]} is not version {pkg.version} of {dist}")
        subprocess.run(
            [
                "uv",
                "export",
                "-q",
                "--package",
                dist,
                "--frozen",
                "--no-dev",
                "--no-emit-workspace",
                "--no-header",
                "--format",
                "requirements-txt",
                "-o",
                str(out / REQUIREMENTS),
            ],
            cwd=agent_packages.ROOT,
            check=True,
        )
        data["python"] = {"module": meta["module"], "wheels": wheels, "requirements": REQUIREMENTS}
    elif pkg.kind == "node":
        if pkg.engines_node is None:
            raise SystemExit(f"{pkg.path}/package.json needs engines.node as '>=X.Y.Z'")
        if not list(out.glob(meta["asset"].replace("{platform}", "*"))):
            raise SystemExit(f"no {meta['asset']} in {out}")
        data["node"] = {
            "version": meta["node"],
            "min": pkg.engines_node,
            "asset": meta["asset"],
            "entry": meta["entry"],
        }
    else:
        if not list(out.glob(meta["asset"].replace("{target}", "*"))):
            raise SystemExit(f"no {meta['asset']} in {out}")
        data["binary"] = {
            "name": meta["binary"],
            "asset": meta["asset"],
            "gpu_asset": meta.get("gpu_asset"),
            "gpu_setup": meta.get("gpu_setup", []),
        }
    return ReleaseManifest.model_validate(data).model_dump(mode="json", exclude_none=True)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    agent, out = sys.argv[1], Path(sys.argv[2])
    data = manifest(agent, out)
    (out / FILENAME).write_text(json.dumps(data, indent=2) + "\n")
    print(f"✓ {out / FILENAME}: {agent} {data['version']} ({data['kind']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

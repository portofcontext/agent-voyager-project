"""Keep agents.json pinned to each built-in agent's package version.

The CLI installs the release of each agent that agents.json names. That is
always the agent's own package version: bump the version in the agent's
package, run `make pins`, and the CLI pins it (`make release-cli` then cuts
any agent release that doesn't exist yet). With --check, report drift instead
of fixing it (the CLI's tests run this).

Usage: python avp/scripts/agent-pins.py [--check]
"""

from __future__ import annotations

import json
import sys

import agent_packages


def main() -> int:
    check = sys.argv[1:] == ["--check"]
    data = agent_packages.registry()
    drift = []
    for name, entry in data.items():
        version = agent_packages.read(name).version
        if entry["version"] != version:
            drift.append(f"{name}: agents.json pins {entry['version']}, the package is {version}")
            entry["version"] = version
    if not drift:
        return 0
    if check:
        print("agents.json is stale; run `make pins`:\n  " + "\n  ".join(drift))
        return 1
    lines = ",\n".join(f"  {json.dumps(name)}: {json.dumps(entry)}" for name, entry in data.items())
    agent_packages.REGISTRY.write_text("{\n" + lines + "\n}\n")
    print("\n".join(drift))
    return 0


if __name__ == "__main__":
    sys.exit(main())

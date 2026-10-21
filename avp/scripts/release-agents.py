"""Make sure the agent releases the CLI pins exist, cutting any that don't.

For each agent (all of agents.json by default), the release the CLI pins is
`agent-<name>-v<version>`. One that is published with its avp-release.json is
done. One whose tag is pushed but isn't published yet is still building, or
its workflow failed (the release workflow publishes only after the release
passes its smoke run), so this waits for it. One with no tag is cut from HEAD
and pushed, then waited for. It exits nonzero unless every pinned release ends
up published, which is what `make release-cli` needs before it tags the CLI.

Run from a clean main in sync with origin (the Makefile's _release-guard).

With --dry-run, report what it would cut and push nothing.

Usage: uv run python avp/scripts/release-agents.py [--dry-run] [agent ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

import agent_packages

MANIFEST = "avp-release.json"


def _run(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _published(tag: str) -> bool:
    result = _run("gh", "release", "view", tag, "--json", "assets", check=False)
    if result.returncode != 0:
        return False
    return MANIFEST in {a["name"] for a in json.loads(result.stdout)["assets"]}


def _tag_pushed(tag: str) -> bool:
    return bool(_run("git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}").stdout.strip())


def _run_for(agent: str, tag: str) -> dict | None:
    """The newest release-workflow run for `tag`, waiting a little for a run
    that was just triggered to appear."""
    for _ in range(30):
        result = _run(
            "gh",
            "run",
            "list",
            "--workflow",
            f"release-{agent}.yml",
            "--branch",
            tag,
            "--limit",
            "1",
            "--json",
            "databaseId,status,conclusion,url",
            check=False,
        )
        # A failed lookup (a GitHub API hiccup) is retried like an empty one.
        runs = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else []
        if runs:
            return runs[0]
        time.sleep(10)
    return None


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # progress shows up live when logged
    registry = agent_packages.registry()
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    agents = [a for a in args if a != "--dry-run"] or list(registry)
    unknown = [a for a in agents if a not in registry]
    if unknown:
        print(f"error: not built-in agents: {', '.join(unknown)}")
        return 2
    waiting: dict[str, str] = {}
    for agent in agents:
        tag = f"agent-{agent}-v{registry[agent]['version']}"
        if _published(tag):
            print(f"✓ {tag} is published")
            continue
        if _tag_pushed(tag):
            print(f"… {tag} is pushed but not published; checking its release run")
        elif dry_run:
            print(f"→ would cut {tag}")
            continue
        else:
            print(f"→ cutting {tag}")
            _run("git", "tag", "-a", tag, "-m", f"{agent} agent {registry[agent]['version']}")
            _run("git", "push", "origin", tag)
        waiting[agent] = tag

    if dry_run:
        return 0
    failed = []
    for agent, tag in waiting.items():
        run = _run_for(agent, tag)
        if run is None:
            failed.append(f"{tag}: no release-{agent}.yml run found")
            continue
        print(f"… waiting on {tag}: {run['url']}")
        _run("gh", "run", "watch", str(run["databaseId"]), "--exit-status", check=False)
        if _published(tag):
            print(f"✓ {tag} is published")
        else:
            failed.append(f"{tag}: its release run didn't publish it ({run['url']})")

    if failed:
        print("\nnot published:\n  " + "\n  ".join(failed))
        print(
            "fix the cause on main, bump that agent's version, `make pins`, and release again"
            " (a pushed tag is never moved)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The built-in agents' published images: what the Agent images workflow
builds, and the digests the CLI pins.

    python scripts/agent-images.py matrix   # one JSON entry per agent, for the workflow
    python scripts/agent-images.py pin      # write each published image's digest to builtins.json

An image is `ghcr.io/portofcontext/<agent_name>:<version>`, built from the
source commit in builtins.json with the CLI's Dockerfile for the agent. `pin`
fails when an agent's version has no published image.
"""

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILTINS = ROOT / "avp-cli/src/avp_cli/agents/builtins.json"
REGISTRY = "ghcr.io"
OWNER = "portofcontext"
MANIFESTS = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)


def repository(agent: dict[str, str]) -> str:
    return f"{OWNER}/{agent['agent_name']}"


def matrix(catalog: dict) -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "directory": agent["directory"],
            "image": f"{REGISTRY}/{repository(agent)}:{agent['version']}",
            "commit": catalog["commit"],
        }
        for name, agent in catalog["agents"].items()
    ]


def digest(repository: str, tag: str) -> str:
    """The digest the registry serves for the tag, read without credentials."""
    try:
        with urllib.request.urlopen(
            f"https://{REGISTRY}/token?service={REGISTRY}&scope=repository:{repository}:pull"
        ) as response:
            token = json.load(response)["token"]
        request = urllib.request.Request(
            f"https://{REGISTRY}/v2/{repository}/manifests/{tag}",
            method="HEAD",
            headers={"Authorization": f"Bearer {token}", "Accept": ", ".join(MANIFESTS)},
        )
        with urllib.request.urlopen(request) as response:
            found = response.headers["Docker-Content-Digest"]
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"{REGISTRY}/{repository}:{tag} is not published or not public ({exc.code}). "
            "Run the Agent images workflow, and make the package public."
        ) from None
    if not found or not found.startswith("sha256:"):
        raise SystemExit(f"{REGISTRY}/{repository}:{tag} has no SHA-256 digest")
    return found


def pin(catalog: dict) -> None:
    for name, agent in catalog["agents"].items():
        tag = agent["version"]
        agent["image"] = f"{REGISTRY}/{repository(agent)}:{tag}@{digest(repository(agent), tag)}"
        print(f"{name}: {agent['image']}")
    BUILTINS.write_text(json.dumps(catalog, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["matrix", "pin"])
    arguments = parser.parse_args()
    catalog = json.loads(BUILTINS.read_text())
    if arguments.command == "matrix":
        print(json.dumps(matrix(catalog)))
    else:
        pin(catalog)

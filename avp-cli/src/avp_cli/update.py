"""`avp update`: install the newest CLI release from GitHub, then bring the
installed built-in agents to the versions it pins."""

import json
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Annotated, NamedTuple

import httpx
import typer
from packaging.version import InvalidVersion, Version

from avp_cli import console
from avp_cli._cli_common import VerboseOption
from avp_cli.console import Failed, detail, err, out

RELEASES = "https://api.github.com/repos/portofcontext/agent-voyager-project/releases"
TAG = "cli-v"
PACKAGE = "avp-cli"
RECEIPT = "uv-receipt.toml"
"""In the environment of a tool uv installed."""


class Release(NamedTuple):
    version: Version
    wheel: str
    """The wheel's download URL."""


def current() -> Version:
    return Version(metadata.version(PACKAGE))


def releases() -> list[Release]:
    """The CLI's published releases that have a wheel."""
    try:
        response = httpx.get(
            RELEASES,
            params={"per_page": 100},
            headers={"accept": "application/vnd.github+json", "user-agent": PACKAGE},
            timeout=30,
            follow_redirects=True,
        )
        response.raise_for_status()
        listed = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise Failed(f"couldn't list the releases at {RELEASES}: {error}") from None
    found = []
    for release in listed:
        tag = release.get("tag_name", "")
        if not tag.startswith(TAG) or release.get("draft"):
            continue
        try:
            version = Version(tag.removeprefix(TAG))
        except InvalidVersion:
            continue
        wheels = [
            a["browser_download_url"] for a in release["assets"] if a["name"].endswith(".whl")
        ]
        if wheels:
            found.append(Release(version, wheels[0]))
    return found


def newest(found: list[Release], installed: Version, pre: bool) -> Release | None:
    """The highest release above `installed`. A prerelease counts only with
    `pre`, or when `installed` is one."""
    allowed = [r for r in found if pre or installed.is_prerelease or not r.version.is_prerelease]
    best = max(allowed, key=lambda r: r.version, default=None)
    return best if best and best.version > installed else None


def checkout() -> str | None:
    """The checkout this avp runs from, when it was installed editable."""
    text = metadata.distribution(PACKAGE).read_text("direct_url.json")
    url = json.loads(text) if text else {}
    return url.get("url") if url.get("dir_info", {}).get("editable") else None


def update(
    check: Annotated[
        bool, typer.Option("--check", help="Say whether a newer release exists, and stop.")
    ] = False,
    pre: Annotated[bool, typer.Option("--pre", help="Count prereleases as newer.")] = False,
    verbose: VerboseOption = False,
) -> None:
    """Install the newest avp release, then reinstall the built-in agents whose
    versions it changed."""
    console.set_verbose(verbose)
    installed = current()
    release = newest(releases(), installed, pre)
    if release is None:
        out.print(f"avp {installed} is the newest release", highlight=False)
        return
    command = ["uv", "tool", "install", "--force", release.wheel]
    if check:
        out.print(f"avp {release.version} is available; this is {installed}", highlight=False)
        return
    if source := checkout():
        raise Failed(
            f"this avp runs from a checkout, {source}. Update the checkout, or install "
            f"{release.version} with: {' '.join(command)}"
        )
    if not (Path(sys.prefix) / RECEIPT).is_file() or not shutil.which("uv"):
        raise Failed(
            f"avp {release.version} is available, but this avp wasn't installed with "
            f"`uv tool install`. Install the wheel with your installer: {release.wheel}"
        )
    with err.status(f"Installing avp {release.version}"):
        done = subprocess.run(command, capture_output=True, text=True)
    detail(done.stderr.strip())
    if done.returncode != 0:
        raise Failed(f"`{' '.join(command)}` failed:\n{done.stderr.strip()}")
    err.print(f"Updated avp {installed} to {release.version}", highlight=False)
    # The new release knows its own agent versions; this process has the old ones.
    agents = subprocess.run([sys.argv[0], "agent", "update"])
    if agents.returncode != 0:
        raise typer.Exit(agents.returncode)

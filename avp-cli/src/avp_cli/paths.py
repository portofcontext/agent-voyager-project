"""Where avp keeps its state: `$AVP_HOME`, or `~/.avp`."""

import os
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("AVP_HOME") or Path.home() / ".avp")


def agents() -> Path:
    """One `<name>.json` per installed agent."""
    return home() / "agents"


def runs() -> Path:
    """One directory per run: its Commission and Trajectory."""
    return home() / "runs"


def opensandbox() -> Path:
    """The OpenSandbox service's config, database, log, and pid file."""
    return home() / "opensandbox"

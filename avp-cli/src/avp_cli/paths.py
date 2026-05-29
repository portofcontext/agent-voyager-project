"""Where `avp` keeps its assets.

Everything the CLI manages lives under one root, `~/.avp` (override with the
`AVP_HOME` env var): the portable **commission library**, the **run outputs**
(trajectories + history), and **installed agents** (prebuilt artifacts the CLI
runs). The one thing that does *not* live here is the eval config file itself —
`avp init` writes that in place, in your project, so it's easy to find, edit,
and commit alongside your code.
"""

from __future__ import annotations

import os
from pathlib import Path


def avp_home() -> Path:
    """The asset root: `$AVP_HOME` or `~/.avp`."""
    env = os.environ.get("AVP_HOME")
    return Path(env).expanduser() if env else Path.home() / ".avp"


def commissions_dir() -> Path:
    """The portable commission library: `~/.avp/commissions/<id>.json`."""
    return avp_home() / "commissions"


def runs_dir() -> Path:
    """Eval run outputs + history: `~/.avp/runs/<voyage-id>/`."""
    return avp_home() / "runs"


def agents_dir() -> Path:
    """Installed agents: `~/.avp/agents/<name>/`.

    Each subdir holds one installed agent: the generated `avp-conformance.json`
    manifest the CLI drives, an `installed.json` provenance record, and the
    artifact itself (`bin/<binary>` for a prebuilt binary agent, `venv/` for a
    Python agent). `avp agent install` writes these; `resolve_agent` prefers them
    over the in-repo dev fallback.
    """
    return avp_home() / "agents"

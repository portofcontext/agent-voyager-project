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


def environments_dir() -> Path:
    """Declarative agent environments: `~/.avp/environments/<name>.json`."""
    return avp_home() / "environments"


def agents_dir() -> Path:
    """Installed agents: `~/.avp/agents/<name>/`.

    Each subdir holds one installed agent and its `installed.json` record of
    where it came from (an avp release, a manifest, or a local build). Release
    and local installs also hold the generated `avp-conformance.json` the CLI
    drives on the host and the artifact itself (`bin/<binary>`, `venv/`, or
    `app/`); a local build keeps its sandbox artifacts in `artifacts/`.
    `avp agent install` writes these, and `resolve_agent` only runs what's here.
    """
    return avp_home() / "agents"

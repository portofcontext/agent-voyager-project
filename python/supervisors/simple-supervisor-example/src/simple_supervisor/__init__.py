"""simple-supervisor-example — a worked AVP v0.1 supervisor.

Build Configs from Profiles, drive a agent subprocess (or in-process), surface
the trajectory (what the agent did, the run cost).
"""

from __future__ import annotations

from simple_supervisor.agent import run_subprocess, stream_subprocess
from simple_supervisor.builder import build_commission
from simple_supervisor.observability import (
    Summary,
    ToolUsage,
    render,
    summarize,
)
from simple_supervisor.profiles import (
    DEV_LOOSE,
    PRESETS,
    READ_ONLY,
    Profile,
    get_profile,
)

__all__ = [
    "DEV_LOOSE",
    "PRESETS",
    "READ_ONLY",
    "Profile",
    "Summary",
    "ToolUsage",
    "build_commission",
    "get_profile",
    "render",
    "run_subprocess",
    "stream_subprocess",
    "summarize",
]

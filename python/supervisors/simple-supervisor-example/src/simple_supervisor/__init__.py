"""simple-supervisor-example — a worked AEP v0.1 supervisor.

Build Configs from Profiles, drive a runner subprocess (or in-process), surface
the trajectory in three classes (what the agent did / rules said / run cost).
"""

from __future__ import annotations

from simple_supervisor.builder import build_config
from simple_supervisor.observability import (
    Summary,
    ToolUsage,
    VerifierResult,
    render,
    summarize,
)
from simple_supervisor.profiles import (
    COST_BOUNDED,
    DDD_STRICT,
    DEV_LOOSE,
    PRESETS,
    QUALITY_GUARDS,
    Profile,
    get_profile,
)
from simple_supervisor.runner import run_subprocess, stream_subprocess

__all__ = [
    "COST_BOUNDED",
    "DDD_STRICT",
    "DEV_LOOSE",
    "PRESETS",
    "QUALITY_GUARDS",
    "Profile",
    "Summary",
    "ToolUsage",
    "VerifierResult",
    "build_config",
    "get_profile",
    "render",
    "run_subprocess",
    "stream_subprocess",
    "summarize",
]

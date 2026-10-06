"""Commission -> the harness's own configuration. REPLACE the body.

Map every Commission field the harness can honor (model, system prompt, the
`enabled_builtin_*` allow-lists under this agent's key, inline `mcp_servers`
and `skills`) onto the harness's config before the run starts.
"""

from __future__ import annotations

import dataclasses

from avp.commission import Commission
from avp.trajectory import ErrorCode

AGENT_NAME = "avp-agent-template"
BUILTIN_TOOLS = ["echo"]


@dataclasses.dataclass
class HarnessConfig:
    model: str
    prompt: str
    system_prompt: str | None
    tools: list[str]


def from_commission(commission: Commission) -> HarnessConfig:
    allow = (commission.enabled_builtin_tools or {}).get(AGENT_NAME)
    return HarnessConfig(
        model=commission.model,
        prompt=commission.prompt or "",
        system_prompt=commission.system_prompt,
        tools=[t for t in BUILTIN_TOOLS if allow is None or t in allow],
    )


ALLOWLISTS = (
    "enabled_builtin_tools",
    "enabled_builtin_subagents",
    "enabled_builtin_skills",
    "enabled_builtin_mcp_servers",
)


def fail_fast(commission: Commission, agent_version: str) -> tuple[ErrorCode, str] | None:
    """Commission checks the spec requires before any model turn: a version
    pin for a different build, an allow-list map without this agent's key, or
    an allow-listed tool the agent doesn't offer."""
    pin = (commission.agent_versions or {}).get(AGENT_NAME)
    if pin is not None and pin != agent_version:
        return ErrorCode.unsupported_agent_version, f"Commission pins {AGENT_NAME} at {pin!r}"
    missing = [
        f for f in ALLOWLISTS if (m := getattr(commission, f)) is not None and AGENT_NAME not in m
    ]
    if missing:
        return ErrorCode.commission_collision, f"no {AGENT_NAME!r} entry in: {', '.join(missing)}"
    unknown = [
        t
        for t in (commission.enabled_builtin_tools or {}).get(AGENT_NAME) or []
        if t not in BUILTIN_TOOLS
    ]
    if unknown:
        return ErrorCode.commission_collision, f"tools not offered: {', '.join(unknown)}"
    return None

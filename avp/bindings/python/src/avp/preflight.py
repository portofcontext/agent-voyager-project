"""avp.preflight — the Commission checks every agent runs before its first turn.

The spec requires an agent to refuse a Commission it can't honor before any
model turn, with ``error_occurred`` + ``agent_stopped(error)``:

- ``agent_versions`` pins this agent at a different build
  (``unsupported_agent_version``);
- an ``enabled_builtin_*`` allow-list map has no entry under this agent's name
  (``commission_collision``): it filters a surface the Commission wasn't
  authored for here;
- an allow-list names a tool / subagent / skill / MCP server the agent doesn't
  offer (``commission_collision``).

Pass the names the agent offers for each surface; a surface left as ``None``
is not checked by name. Harness-specific refusals (an unreachable provider or
model) stay in the adapter.

    if failure := preflight(commission, agent_name=NAME, agent_version=VERSION, tools=offered):
        await rec.error(*failure)
        await rec.stop(StopReason.error)
        return
"""

from __future__ import annotations

from collections.abc import Iterable

from avp.commission import Commission
from avp.trajectory import ErrorCode

ALLOWLISTS = (
    "enabled_builtin_tools",
    "enabled_builtin_subagents",
    "enabled_builtin_skills",
    "enabled_builtin_mcp_servers",
)


def preflight(
    commission: Commission,
    *,
    agent_name: str,
    agent_version: str,
    tools: Iterable[str] | None = None,
    subagents: Iterable[str] | None = None,
    skills: Iterable[str] | None = None,
    mcp_servers: Iterable[str] | None = None,
) -> tuple[ErrorCode, str] | None:
    """The first Commission check that fails, as ``(code, message)``, or None."""
    pin = (commission.agent_versions or {}).get(agent_name)
    if pin is not None and pin != agent_version:
        return (
            ErrorCode.unsupported_agent_version,
            f"Commission pins {agent_name} at {pin!r}; this build is {agent_version!r}",
        )
    missing = [
        f for f in ALLOWLISTS if (m := getattr(commission, f)) is not None and agent_name not in m
    ]
    if missing:
        return ErrorCode.commission_collision, f"no {agent_name!r} entry in: {', '.join(missing)}"
    offered = zip(ALLOWLISTS, (tools, subagents, skills, mcp_servers), strict=True)
    for field, names in offered:
        allowed = (getattr(commission, field) or {}).get(agent_name)
        if names is None or allowed is None:
            continue
        known = set(names)
        unknown = [n for n in allowed if n not in known]
        if unknown:
            return (
                ErrorCode.commission_collision,
                f"{field} names not offered by the agent: {', '.join(unknown)}",
            )
    return None

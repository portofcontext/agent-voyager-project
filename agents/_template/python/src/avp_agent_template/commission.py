"""Commission -> the harness's own configuration. REPLACE the body.

Map every Commission field the harness can honor (model, system prompt, the
`enabled_builtin_*` allow-lists under this agent's key, inline `mcp_servers`
and `skills`) onto the harness's config before the run starts.
"""

from __future__ import annotations

import dataclasses

from avp.commission import Commission

AGENT_NAME = "avp-agent-template"
# What the harness ships with, mirrored onto the descriptor. The stand-in
# harness ships one `echo` tool; replace this with your harness's real
# defaults (a product such as Claude Code or Goose), or `[]` for a framework
# whose agents ship nothing (the OpenAI Agents SDK). Never add tools the
# harness doesn't ship: the supervisor supplies extra tools through the
# Commission's `mcp_servers`.
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

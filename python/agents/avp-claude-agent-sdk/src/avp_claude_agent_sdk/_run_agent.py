"""`run_avp_agent` -- Commission-driven entry point for AVPClaudeSDKClient.

## Commission → ClaudeAgentOptions mapping

| Commission field              | ClaudeAgentOptions field        | Notes                                                                        |
|-------------------------------|---------------------------------|------------------------------------------------------------------------------|
| `model`                       | `model`                         | Direct.                                                                      |
| `system_prompt`               | `system_prompt`                 | Direct.                                                                      |
| `prompt`                      | *(connect / query call arg)*    | Not an option field; passed as the prompt arg when calling `query()`.        |
| `mcp_servers` (managed refs)  | `mcp_servers` dict              | Refs resolved by the AVP Resolver → `McpServerConfig` values; merged dict.  |
| `skills` (managed refs)       | `skills` list                   | Refs resolved → skill names; merged with `enabled_builtin_skills` list.     |
| `enabled_builtin_tools`       | `tools`                         | `None` → SDK default; `[]` → `tools=[]`; list → `tools=list`.              |
| `enabled_builtin_skills`      | `skills`                        | Merged with resolved managed skill names (union exposed to the model).       |
| `enabled_builtin_mcp_servers` | *(no clean mapping)*            | No per-server filter in SDK options. Workaround: `strict_mcp_config=True`   |
|                               |                                 | + pass only the listed server configs in `mcp_servers`. Loses built-in CLI  |
|                               |                                 | servers not in the Commission. TODO: confirm with SDK team.                  |
| `enabled_builtin_subagents`   | *(no clean mapping)*            | `options.agents` defines custom agents, not filters built-in ones. The SDK  |
|                               |                                 | has no `disallowed_agents` / `allowed_agents` knob. Enforcement would have  |
|                               |                                 | to be in-loop (reject hallucinated Agent calls not in the allowlist).        |
| `subagents` (managed refs)    | `agents` dict                   | Partial: resolved subagent definitions could be injected as `AgentDefinition`|
|                               |                                 | values, but the resolver returns SKILL.md-style content, not SDK agent defs. |
|                               |                                 | Shape mismatch -- TODO defer to v0.2.                                        |
| `output_schema`               | *(no equivalent)*               | No SDK field. Must be injected into the system prompt as a JSON Schema        |
|                               |                                 | instruction if needed.                                                       |
| `run_id`                      | `session_id`                    | Partial: Commission run_id is AVP-level; SDK session_id controls persistence.|
|                               |                                 | Passing run_id as session_id ties AVP and SDK namespaces -- may cause UUID   |
|                               |                                 | format conflicts. Safer to keep them separate and record both.               |
| `supervisor`                  | *(AVP-only)*                    | Stamped on `run_requested` event; no SDK field.                              |
| `thread_id`                   | *(no equivalent)*               | No SDK field. AVP metadata only.                                             |
| `tags`                        | *(no equivalent)*               | No SDK field. AVP metadata only.                                             |
| `meta`                        | *(no equivalent)*               | No SDK field. AVP metadata only.                                             |
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from avp.agent.sink import EventSink, stdio_sink
from avp.commission import Commission
from avp_claude_agent_sdk._client import AVPClaudeSDKClient


async def run_avp_agent(
    commission: Commission,
    agent_main: Callable[[AVPClaudeSDKClient], Awaitable[Any]],
    sink: EventSink = stdio_sink,
) -> None:
    """Run an AVP-instrumented agent session driven by a Commission.

    Constructs an `AVPClaudeSDKClient` from the Commission (model,
    system_prompt, resolved MCP servers/skills), then calls
    `agent_main(client)` -- the caller owns `query()` /
    `receive_response()`. Guarantees `agent_stopped` is emitted in a
    `finally` block regardless of how `agent_main` exits.

    Args:
        commission: Supervisor-provided run configuration.
        agent_main: Async callable that receives the ready client and drives
            the session (calls `query()`, iterates `receive_response()`, etc.).
        sink: AVP event sink. Defaults to stdio (NDJSON to stdout).
    """
    # TODO: resolve commission.mcp_servers / .skills / .subagents via AVP
    # Resolver API before constructing options. For now, use only the fields
    # that map directly without resolution.
    options = _commission_to_options(commission)
    async with AVPClaudeSDKClient(options=options, sink=sink) as client:
        await agent_main(client)


def _commission_to_options(commission: Commission):  # type: ignore[return]
    """Translate Commission fields to ClaudeAgentOptions.

    Only the directly-mappable fields are handled here. Fields that require
    Resolver API calls (mcp_servers, skills, subagents refs) or have no SDK
    equivalent (thread_id, tags, meta, output_schema, enabled_builtin_subagents)
    are left as TODOs.
    """
    from claude_agent_sdk.types import ClaudeAgentOptions

    # --- direct ---
    model = commission.model
    system_prompt = commission.system_prompt

    # --- enabled_builtin_tools → options.tools ---
    # None   = SDK default (all tools).
    # []     = disable all tools.
    # [...]  = expose exactly this set.
    tools = commission.enabled_builtin_tools  # None | list[str]

    # --- enabled_builtin_skills → options.skills ---
    # TODO: merge with resolved managed skill names once Resolver is wired.
    skills = commission.enabled_builtin_skills  # None | list[str]

    # TODO: enabled_builtin_mcp_servers -- no clean SDK knob; defer.
    # TODO: enabled_builtin_subagents -- no SDK allowlist knob; defer.
    # TODO: mcp_servers managed refs -- resolve via AVP Resolver → McpServerConfig dict.
    # TODO: skills managed refs -- resolve via AVP Resolver → skill names, merge above.
    # TODO: subagents managed refs -- shape mismatch with SDK AgentDefinition; defer to v0.2.
    # TODO: output_schema -- inject into system_prompt if set.
    # TODO: run_id / session_id -- decide coupling strategy.

    return ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        skills=skills,
    )

"""What a run uses and what it turns off, from the Commission and the agent's
Descriptor.

Follows the Commission spec's rules for agents: agent settings limit the
built-in items, added items are used, and `system_prompt` replaces the agent's
own. Call it on a Commission that passed `check_commission`.

    plan = plan_run(commission, descriptor)
    # configure the runtime from plan.started; hide and block plan.turned_off
    # after connecting, add each MCP server's status and tools:
    await rec.start(plan.started.model_copy(update={"mcp_servers": ..., "tools": ...}))
"""

from pydantic import BaseModel

from avp.commission import AgentSettings, Commission, ModelRef
from avp.descriptor import AgentDescriptor, McpServer, Skill
from avp.trajectory import AgentStarted
from avp.utils._skill_md import frontmatter_value


class TurnedOff(BaseModel):
    """The built-in items the Commission turns off, by name (MCP servers by
    id), in the Descriptor's order. The agent hides them from the model and
    refuses calls to them."""

    tools: list[str]
    """Built-in tools, and the tools of turned-off built-in MCP servers."""
    subagents: list[str]
    skills: list[str]
    mcp_servers: list[str]


class RunPlan(BaseModel):
    started: AgentStarted
    """What the run uses. The Commission's MCP servers have no `status` and
    their tools aren't listed: the agent adds both after connecting, and each
    added skill's `source` once it has written the skill's files."""
    turned_off: TurnedOff


def _allowed(names: list[str], enabled: list[str] | None) -> set[str]:
    return set(names) if enabled is None else set(enabled)


def plan_run(commission: Commission, descriptor: AgentDescriptor) -> RunPlan:
    """The run's plan. An absent `enabled_*` list allows every built-in item of
    its kind, a present one only the items it names; the Commission's own MCP
    servers and skills are always used."""
    settings = (commission.agents or {}).get(descriptor.agent_name) or AgentSettings()
    builtin_tools = [t for t in descriptor.tools or [] if t.mcp_server_id is None]
    servers = descriptor.mcp_servers or []
    subagents = descriptor.subagents or []
    skills = descriptor.skills or []

    tools_on = _allowed([t.name for t in builtin_tools], settings.enabled_tools)
    servers_on = _allowed([s.id for s in servers], settings.enabled_mcp_servers)
    subagents_on = _allowed([s.name for s in subagents], settings.enabled_subagents)
    skills_on = _allowed([s.name for s in skills], settings.enabled_skills)

    def tool_on(name: str, mcp_server_id: str | None) -> bool:
        return name in tools_on if mcp_server_id is None else mcp_server_id in servers_on

    started = AgentStarted(
        prompt=commission.prompt,
        system_prompt=commission.system_prompt or descriptor.system_prompt,
        model=ModelRef.model_validate(commission.model.model_dump(exclude={"credential"})),
        tools=[t for t in descriptor.tools or [] if tool_on(t.name, t.mcp_server_id)] or None,
        mcp_servers=[
            *(s for s in servers if s.id in servers_on),
            *(
                McpServer(id=s.id, name=s.name, description=s.description)
                for s in commission.mcp_servers or []
            ),
        ]
        or None,
        skills=[
            *(s for s in skills if s.name in skills_on),
            *(
                Skill(
                    name=s.name,
                    description=frontmatter_value(s.files["SKILL.md"], "description") or "",
                )
                for s in commission.skills or []
            ),
        ]
        or None,
        subagents=[s for s in subagents if s.name in subagents_on] or None,
    )
    turned_off = TurnedOff(
        tools=[t.name for t in descriptor.tools or [] if not tool_on(t.name, t.mcp_server_id)],
        subagents=[s.name for s in subagents if s.name not in subagents_on],
        skills=[s.name for s in skills if s.name not in skills_on],
        mcp_servers=[s.id for s in servers if s.id not in servers_on],
    )
    return RunPlan(started=started, turned_off=turned_off)

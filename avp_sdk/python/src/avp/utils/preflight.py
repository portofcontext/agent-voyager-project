"""The checks an agent runs on a Commission before the run starts.

Covers the cases in the Commission spec's "The agent checks the Commission
before the run starts" (`spec/v0.1/commission.md`) that need only the
Commission and the agent's Descriptor. The agent checks the model cases itself:
whether it can call `model.provider` or `model.base_url`, and whether the
service offers `model.id`.
"""

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.utils._skill_md import frontmatter_value


def check_agent_entry(commission: Commission, descriptor: AgentDescriptor) -> str | None:
    """MUST refuse: `agents` is present and has no entry for the agent's `agent_name`."""
    if commission.agents is not None and descriptor.agent_name not in commission.agents:
        return f"agents has no entry for {descriptor.agent_name!r}"
    return None


def check_agent_version(commission: Commission, descriptor: AgentDescriptor) -> str | None:
    """MUST refuse: the agent's entry has a `version` that differs from its `agent_version`."""
    settings = (commission.agents or {}).get(descriptor.agent_name)
    if settings and settings.version is not None and settings.version != descriptor.agent_version:
        return (
            f"agents.{descriptor.agent_name}.version is {settings.version!r}, "
            f"but this agent is version {descriptor.agent_version!r}"
        )
    return None


def check_enabled_items(commission: Commission, descriptor: AgentDescriptor) -> str | None:
    """MUST refuse: an `enabled_*` list in the agent's entry names an item that
    isn't in the matching list of its Descriptor. For `enabled_tools`, only
    tools without an `mcp_server_id` count."""
    settings = (commission.agents or {}).get(descriptor.agent_name)
    if settings is None:
        return None
    offered = {
        "enabled_tools": {t.name for t in descriptor.tools or [] if t.mcp_server_id is None},
        "enabled_subagents": {s.name for s in descriptor.subagents or []},
        "enabled_skills": {s.name for s in descriptor.skills or []},
        "enabled_mcp_servers": {s.id for s in descriptor.mcp_servers or []},
    }
    for field, names in offered.items():
        enabled: list[str] | None = getattr(settings, field)
        unknown = [name for name in enabled or [] if name not in names]
        if unknown:
            return (
                f"agents.{descriptor.agent_name}.{field} names items the agent "
                f"doesn't have: {', '.join(unknown)}"
            )
    return None


def check_skill_names(commission: Commission, descriptor: AgentDescriptor) -> str | None:
    """MUST refuse: a skill's `name` differs from the `name` in the frontmatter
    of its `SKILL.md`."""
    for skill in commission.skills or []:
        name = frontmatter_value(skill.files["SKILL.md"], "name")
        if name != skill.name:
            found = "has no name" if name is None else f"names {name!r}"
            return f"skill {skill.name!r}: the frontmatter of its SKILL.md {found}"
    return None


def check_added_items_clash(commission: Commission, descriptor: AgentDescriptor) -> str | None:
    """SHOULD refuse: the Commission adds an MCP server whose `id` matches one in
    the agent's Descriptor, or a skill whose name matches one there."""
    builtin_servers = {s.id for s in descriptor.mcp_servers or []}
    for server in commission.mcp_servers or []:
        if server.id in builtin_servers:
            return f"MCP server {server.id!r} has the same id as one the agent comes with"
    builtin_skills = {s.name for s in descriptor.skills or []}
    for skill in commission.skills or []:
        if skill.name in builtin_skills:
            return f"skill {skill.name!r} has the same name as one the agent comes with"
    return None


CHECKS = (
    check_agent_entry,
    check_agent_version,
    check_enabled_items,
    check_skill_names,
    check_added_items_clash,
)
"""Every check, in the spec's order. An agent that skips the SHOULD case runs
the others itself."""


def check_commission(commission: Commission, descriptor: AgentDescriptor) -> str | None:
    """The first refusal case the Commission falls under, as the message for its
    `error_occurred`, or None when it falls under none.

    The `error_occurred` code is always `invalid_commission`. Runs every check in
    `CHECKS`, the SHOULD case included.
    """
    for check in CHECKS:
        if message := check(commission, descriptor):
            return message
    return None

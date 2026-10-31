"""The checks an agent runs on a Commission before the run starts.

Covers the cases in the Commission spec's "The agent checks the Commission
before the run starts" (`spec/v0.1/commission.md`) that need only the
Commission and the agent's Descriptor. The agent checks the model cases itself:
whether it can call `model.provider` or `model.base_url`, and whether the
service offers `model.id`.
"""

import re

from avp.commission import Commission
from avp.descriptor import AgentDescriptor

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|\Z)", re.DOTALL)
_NAME = re.compile(r"^name:[ \t]*(.*?)[ \t]*$", re.MULTILINE)


def _frontmatter_name(skill_md: str) -> str | None:
    """The `name` in a `SKILL.md`'s frontmatter, or None when it has none.

    Reads only the top-level `name:` line rather than parsing the YAML."""
    frontmatter = _FRONTMATTER.match(skill_md)
    if frontmatter is None:
        return None
    name = _NAME.search(frontmatter.group(1))
    if name is None:
        return None
    value = name.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value.split(" #", 1)[0].rstrip()


def check_commission(commission: Commission, descriptor: AgentDescriptor) -> str | None:
    """The first refusal case the Commission falls under, as the message for its
    `error_occurred`, or None when it falls under none.

    The `error_occurred` code is always `invalid_commission`. Checks the cases in
    the spec's order, the SHOULD case included.
    """
    agent = descriptor.agent_name
    if commission.agents is not None:
        settings = commission.agents.get(agent)
        if settings is None:
            return f"agents has no entry for {agent!r}"
        if settings.version is not None and settings.version != descriptor.agent_version:
            return (
                f"agents.{agent}.version is {settings.version!r}, "
                f"but this agent is version {descriptor.agent_version!r}"
            )
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
                return f"agents.{agent}.{field} names items the agent doesn't have: {', '.join(unknown)}"

    for skill in commission.skills or []:
        name = _frontmatter_name(skill.files["SKILL.md"])
        if name != skill.name:
            found = "has no name" if name is None else f"names {name!r}"
            return f"skill {skill.name!r}: the frontmatter of its SKILL.md {found}"

    builtin_servers = {s.id for s in descriptor.mcp_servers or []}
    for server in commission.mcp_servers or []:
        if server.id in builtin_servers:
            return f"MCP server {server.id!r} has the same id as one the agent comes with"
    builtin_skills = {s.name for s in descriptor.skills or []}
    for skill in commission.skills or []:
        if skill.name in builtin_skills:
            return f"skill {skill.name!r} has the same name as one the agent comes with"

    return None

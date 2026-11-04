"""The cases. Each covers one rule: it writes a Commission for the agent and
checks the run's Trajectory. A case can raise `Skip` when the agent's
Descriptor says it lacks what the rule needs."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from avp.commission import AgentSettings, Commission, McpServerHttp, McpServerStdio, Model, Skill
from avp.descriptor import AgentDescriptor
from avp.trajectory import ErrorOccurredEvent
from avp_cli.eval.scoring import Run

Level = Literal["MUST", "SHOULD"]


class Skip(Exception):
    """The case doesn't apply to the agent. The message says why."""


@dataclass(frozen=True)
class Context:
    """What a case writes its Commission from."""

    descriptor: AgentDescriptor
    model: Model


@dataclass(frozen=True)
class Case:
    name: str
    rule: str
    level: Level
    about: str
    commission: Callable[[Context], Commission]
    check: Callable[[Run], list[str]]
    """The problems with the run, besides an invalid Trajectory or a failed
    exit, which every case fails on; none means it passed."""


RUN_ID = "set-by-the-engine"
"""A Commission must have a `run_id`, and the engine replaces it for each run."""


def _ended_before_start(code: str, message_names: str | None = None) -> Callable[[Run], list[str]]:
    """The run never started: `run_requested`, `agent_described`, then
    `error_occurred` with `code`, and nothing else."""

    def check(run: Run) -> list[str]:
        expected = ["run_requested", "agent_described", "error_occurred"]
        types = [e.type for e in run.trajectory]
        if types != expected:
            return [f"the events are {', '.join(types) or 'none'}; expected {', '.join(expected)}"]
        error = run.trajectory[2]
        if not isinstance(error, ErrorOccurredEvent):
            return []
        if error.data.error_code != code:
            return [f"error_occurred has the code {error.data.error_code}, not {code}"]
        if message_names and message_names not in error.data.error_message:
            return [f"error_occurred's message doesn't name {message_names}"]
        return []

    return check


_refused = _ended_before_start("invalid_commission")

OTHER_AGENT = "avp-conformance-other"
NO_SUCH_ITEM = "avp-conformance-no-such-item"
NO_SUCH_PROVIDER = "avp-conformance-no-such-provider"
SERVER_ID = "avp-conformance-server"
SKILL_NAME = "avp-conformance-skill"
OTHER_SKILL_NAME = "avp-conformance-other-skill"


def _commission(context: Context, **fields: Any) -> Commission:
    return Commission(
        avp_version="0.1", run_id=RUN_ID, model=context.model, prompt="Say hello.", **fields
    )


def _with_settings(context: Context, **settings: Any) -> Commission:
    """A Commission with `settings` in the agent's own entry."""
    return _commission(context, agents={context.descriptor.agent_name: AgentSettings(**settings)})


def _skill(name: str, frontmatter_name: str | None = None) -> Skill:
    frontmatter = f"name: {frontmatter_name or name}\ndescription: A conformance test's skill."
    return Skill(name=name, files={"SKILL.md": f"---\n{frontmatter}\n---\nDo nothing.\n"})


def _no_such_program(id: str) -> McpServerStdio:
    return McpServerStdio(id=id, type="stdio", command=["avp-conformance-no-such-program"])


def _agents_without_entry(context: Context) -> Commission:
    other = OTHER_AGENT
    if context.descriptor.agent_name == other:
        other += "-2"
    return _commission(context, agents={other: AgentSettings()})


def _version_differs(context: Context) -> Commission:
    return _with_settings(context, version=f"{context.descriptor.agent_version}-other")


def _enabled_tools_names_mcp_tool(context: Context) -> Commission:
    """`enabled_tools` covers only tools without an `mcp_server_id`, so a tool
    from a built-in MCP server is unknown to it, unless a tool without one has
    the same name."""
    tools = context.descriptor.tools or []
    own = {t.name for t in tools if not t.mcp_server_id}
    from_mcp = [t.name for t in tools if t.mcp_server_id and t.name not in own]
    if not from_mcp:
        raise Skip("the agent's Descriptor lists no tool from an MCP server")
    return _with_settings(context, enabled_tools=[from_mcp[0]])


def _skill_name_differs(context: Context) -> Commission:
    return _commission(context, skills=[_skill(SKILL_NAME, frontmatter_name=OTHER_SKILL_NAME)])


def _unknown_provider(context: Context) -> Commission:
    """No `base_url`, so nothing tells the agent where this service is."""
    model = context.model.model_copy(update={"provider": NO_SUCH_PROVIDER, "base_url": None})
    return Commission(avp_version="0.1", run_id=RUN_ID, model=model, prompt="Say hello.")


def _added_server_id_taken(context: Context) -> Commission:
    servers = context.descriptor.mcp_servers
    if not servers:
        raise Skip("the agent's Descriptor lists no MCP server")
    try:
        return _commission(context, mcp_servers=[_no_such_program(servers[0].id)])
    except ValidationError:
        raise Skip(f"a Commission can't add a server with the ID {servers[0].id!r}") from None


def _added_skill_name_taken(context: Context) -> Commission:
    skills = context.descriptor.skills
    if not skills:
        raise Skip("the agent's Descriptor lists no skill")
    try:
        return _commission(context, skills=[_skill(skills[0].name)])
    except ValidationError:
        raise Skip(f"a Commission can't add a skill named {skills[0].name!r}") from None


def _stdio_server_wont_start(context: Context) -> Commission:
    return _commission(context, mcp_servers=[_no_such_program(SERVER_ID)])


def _http_server_wont_connect(context: Context) -> Commission:
    server = McpServerHttp(id=SERVER_ID, type="http", url="http://mcp.conformance.invalid/mcp")
    return _commission(context, mcp_servers=[server])


def _refusal(
    name: str, about: str, commission: Callable[[Context], Commission], level: Level = "MUST"
) -> Case:
    return Case(
        name=name,
        rule="commission.5.1",
        level=level,
        about=f"{about}, so it refuses the Commission",
        commission=commission,
        check=_refused,
    )


def _unknown_item(name: str, about: str, field: str) -> Case:
    return _refusal(
        name,
        f"`{field}` names {about} the Descriptor doesn't list",
        lambda context: _with_settings(context, **{field: [NO_SUCH_ITEM]}),
    )


def _connect_failure(name: str, about: str, commission: Callable[[Context], Commission]) -> Case:
    return Case(
        name=name,
        rule="commission.5.4",
        level="MUST",
        about=f"{about}, so the run ends with `mcp_connect_failed`",
        commission=commission,
        check=_ended_before_start("mcp_connect_failed", message_names=SERVER_ID),
    )


CASES: list[Case] = [
    _refusal("agents-without-entry", "`agents` has no entry for the agent", _agents_without_entry),
    _refusal("version-differs", "the agent's entry has another `version`", _version_differs),
    _unknown_item("unknown-enabled-tool", "a tool", "enabled_tools"),
    _unknown_item("unknown-enabled-subagent", "a subagent", "enabled_subagents"),
    _unknown_item("unknown-enabled-skill", "a skill", "enabled_skills"),
    _unknown_item("unknown-enabled-mcp-server", "an MCP server", "enabled_mcp_servers"),
    _refusal(
        "enabled-tools-names-mcp-tool",
        "`enabled_tools` names a tool from a built-in MCP server",
        _enabled_tools_names_mcp_tool,
    ),
    _refusal(
        "skill-name-differs",
        "a skill's `name` differs from the one in its `SKILL.md`",
        _skill_name_differs,
    ),
    _refusal("unknown-provider", "the agent can't call `model.provider`", _unknown_provider),
    _refusal(
        "added-server-id-taken",
        "an added MCP server has the `id` of a built-in one",
        _added_server_id_taken,
        level="SHOULD",
    ),
    _refusal(
        "added-skill-name-taken",
        "an added skill has the name of a built-in one",
        _added_skill_name_taken,
        level="SHOULD",
    ),
    _connect_failure(
        "stdio-server-wont-start",
        "a stdio MCP server's program doesn't exist",
        _stdio_server_wont_start,
    ),
    _connect_failure(
        "http-server-wont-connect",
        "an HTTP MCP server's host doesn't resolve",
        _http_server_wont_connect,
    ),
]

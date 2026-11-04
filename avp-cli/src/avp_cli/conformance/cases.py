"""The cases. Each covers one rule: it writes a Commission for the agent and
checks the run's Trajectory. A case can raise `Skip` when the agent's
Descriptor says it lacks what the rule needs."""

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict

from pydantic import ValidationError

from avp.commission import (
    AgentSettings,
    Commission,
    EnvSecret,
    McpServerHttp,
    McpServerStdio,
    Model,
    Skill,
)
from avp.descriptor import AgentDescriptor
from avp.trajectory import (
    AgentDescribedEvent,
    AgentStarted,
    AgentStartedEvent,
    AssistantMessageEvent,
    ErrorOccurredEvent,
    RunRequestedEvent,
    TextBlock,
    ToolInvokedEvent,
    ToolReturnedEvent,
    ToolUseBlock,
)
from avp_cli.conformance.model_requests import (
    ModelRequest,
    has_credential,
    model_id,
    offered_tools,
    sent_value,
    system_text,
)
from avp_cli.eval.scoring import Run

Level = Literal["MUST", "SHOULD"]

CREDENTIAL_ENV = "AVP_CONFORMANCE_API_KEY"
STAND_IN = "avp-conformance-stand-in"
"""The model's credential in every case: a stand-in in the agent's environment,
for runtimes that won't start without a key. No case reaches a real model."""


class Skip(Exception):
    """The case doesn't apply to the agent. The message says why."""


class ToolCall(TypedDict):
    name: str
    arguments: str
    """The tool's arguments, as JSON text."""


class Usage(TypedDict):
    """A response's token counts. aimock's `usage` names them differently for
    each provider's API, so a case sets all of them."""

    input_tokens: int
    output_tokens: int
    prompt_tokens: int
    completion_tokens: int
    promptTokenCount: int
    candidatesTokenCount: int


class TextResponse(TypedDict):
    content: str
    usage: NotRequired[Usage]


class ToolCallResponse(TypedDict):
    toolCalls: list[ToolCall]
    content: NotRequired[str]
    usage: NotRequired[Usage]


class ResponseError(TypedDict):
    message: str
    type: str


class ErrorResponse(TypedDict):
    error: ResponseError
    status: int


Response = TextResponse | ToolCallResponse | ErrorResponse
"""One model response: the part of aimock's fixture `response` format the cases
use, which aimock answers with in the format of each provider's API. Add a field
when a case needs it. aimock's `FixtureFileResponse` type lists the rest."""


class McpTool(TypedDict):
    """A tool the mock model's MCP server offers, and its answer to one call:
    `result`, or `error` for a call that fails."""

    name: str
    result: NotRequired[str]
    error: NotRequired[str]


@dataclass(frozen=True)
class Context:
    """What a case writes its Commission from."""

    descriptor: AgentDescriptor
    model: Model
    prompt: str = "Say hello."
    mcp_url: str = ""
    """The case's MCP server on the mock model, for a case with `mcp_tools`."""


@dataclass(frozen=True)
class Seen:
    """What a check can compare a run with, besides its Trajectory."""

    descriptor: AgentDescriptor
    """The agent's answer to `describe`."""
    model: Model
    """The model the check names."""
    sent: Commission | None = None
    """The Commission the agent was given."""
    requests: tuple[ModelRequest, ...] = ()
    """The case's requests to the mock model, in order."""
    mcp_requests: tuple[ModelRequest, ...] = ()
    """The case's requests to its MCP server on the mock model, in order."""


@dataclass(frozen=True)
class Case:
    name: str
    rule: str
    level: Level
    about: str
    commission: Callable[[Context], Commission]
    check: Callable[[Run, Seen], list[str]]
    """The problems with the run, besides an invalid Trajectory or a failed
    exit, which every case fails on; none means it passed."""
    responses: tuple[Response, ...] | Callable[[AgentDescriptor], tuple[Response, ...]] = ()
    """The model's responses, in order, or how to write them from the Descriptor.
    A case with responses runs against the mock model."""
    mcp_tools: tuple[McpTool, ...] = ()
    """Tools the case's MCP server on the mock model offers."""
    matches_system_prompt: bool = False
    """Match the model's requests on the system prompt, not the user's message,
    for a case with retries. aimock looks only at the last user message, and a
    retry's holds the agent's complaint, not the prompt. The case's Commission
    sets `system_prompt` to `context.prompt`."""

    @property
    def prompt(self) -> str:
        """The prompt of a case with responses, which is how the mock model
        tells its requests apart. aimock matches part of the message, so the
        brackets stop one case's name matching inside another's."""
        return f"[avp-conformance {self.name}]"

    def scripted(self, descriptor: AgentDescriptor) -> tuple[Response, ...]:
        """The model's responses for this agent."""
        return self.responses if isinstance(self.responses, tuple) else self.responses(descriptor)


RUN_ID = "set-by-the-engine"
"""A Commission must have a `run_id`, and the engine replaces it for each run."""


def _ended_before_start(
    code: str, message_names: str | None = None
) -> Callable[[Run, Seen], list[str]]:
    """The run never started: `run_requested`, `agent_described`, then
    `error_occurred` with `code`, and nothing else."""

    def check(run: Run, seen: Seen) -> list[str]:
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
TOOL_NAME = "avp_conformance_echo"
SYSTEM_PROMPT = "[avp-conformance system prompt]"
SECRET_HEADER = "x-avp-conformance"
REPLY: tuple[Response, ...] = ({"content": "A scripted reply."},)
OFFERS_A_TOOL: tuple[McpTool, ...] = ({"name": TOOL_NAME, "result": "A scripted tool result."},)
CALLS_THE_TOOL: ToolCall = {"name": TOOL_NAME, "arguments": '{"value": "x"}'}
TOOL_ROUND: tuple[Response, ...] = (
    {"toolCalls": [CALLS_THE_TOOL]},
    {"content": "A scripted reply after the tool."},
)
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
MANY_TURNS = 8
"""Enough responses for an agent that retries invalid output before it gives up."""


def _commission(context: Context, **fields: Any) -> Commission:
    return Commission(
        avp_version="0.1", run_id=RUN_ID, model=context.model, prompt=context.prompt, **fields
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


def _events_in_order(run: Run, seen: Seen) -> list[str]:
    """A run that started: `run_requested`, `agent_described`, `agent_started`,
    the run's other events with at least one `assistant_message`, and
    `agent_stopped` last and only once. No two events have the same `id`."""
    types = [e.type for e in run.trajectory]
    repeated = [id for id, count in Counter(e.id for e in run.trajectory).items() if count > 1]
    start = ["run_requested", "agent_described", "agent_started"]
    problems = []
    if types[:3] != start:
        problems.append(
            f"the events start {', '.join(types[:3]) or 'with none'}; expected {', '.join(start)}"
        )
    if not types or types[-1] != "agent_stopped" or types.count("agent_stopped") != 1:
        problems.append(
            f"agent_stopped isn't last and only once in {', '.join(types) or 'no events'}"
        )
    if "assistant_message" not in types:
        problems.append(f"no assistant_message in {', '.join(types) or 'no events'}")
    if repeated:
        problems.append(f"more than one event has the id {', '.join(repeated)}")
    return problems


def _adds_the_mock_mcp_server(context: Context) -> Commission:
    server = McpServerHttp(id=SERVER_ID, type="http", url=context.mcp_url)
    return _commission(context, mcp_servers=[server])


def _every_tool_call_has_a_result(run: Run, seen: Seen) -> list[str]:
    """Each `tool_use` block is followed by a `tool_invoked`, then a
    `tool_returned`, with its ID. This doesn't check that the tool ran: an agent
    that gives MCP tools its own names sees the scripted call as an unknown
    tool, and that call needs a result too."""
    events = run.trajectory
    calls = [
        (position, block.id)
        for position, event in enumerate(events)
        if isinstance(event, AssistantMessageEvent)
        for block in event.data.content
        if isinstance(block, ToolUseBlock)
    ]
    if not calls:
        return ["no assistant_message has a tool_use block"]

    def position_of(kind: type[ToolInvokedEvent | ToolReturnedEvent], id: str) -> int | None:
        return next(
            (
                position
                for position, event in enumerate(events)
                if isinstance(event, kind) and event.data.tool_call_id == id
            ),
            None,
        )

    problems = []
    for message, id in calls:
        invoked = position_of(ToolInvokedEvent, id)
        returned = position_of(ToolReturnedEvent, id)
        if invoked is None:
            problems.append(f"tool call {id} has no tool_invoked")
        elif invoked < message:
            problems.append(f"tool call {id}'s tool_invoked comes before its assistant_message")
        if returned is None:
            problems.append(f"tool call {id} has no tool_returned")
        elif invoked is not None and returned < invoked:
            problems.append(f"tool call {id}'s tool_returned comes before its tool_invoked")
    return problems


def _started(run: Run) -> AgentStarted | None:
    return next((e.data for e in run.trajectory if isinstance(e, AgentStartedEvent)), None)


def _described(run: Run) -> AgentDescriptor | None:
    return next(
        (e.data.descriptor for e in run.trajectory if isinstance(e, AgentDescribedEvent)), None
    )


def _messages(run: Run) -> list[AssistantMessageEvent]:
    return [e for e in run.trajectory if isinstance(e, AssistantMessageEvent)]


NOT_STARTED = ["the run has no agent_started"]
NO_REQUEST = ["the agent sent the mock model no request"]


def _names(owner: Any, attribute: str) -> list[str]:
    """The built-in items of a kind in a Descriptor or an `agent_started`. For
    `tools`, only tools without an `mcp_server_id`, which `enabled_tools` covers."""
    items = getattr(owner, attribute) or []
    if attribute == "tools":
        return [tool.name for tool in items if not tool.mcp_server_id]
    if attribute == "mcp_servers":
        return [server.id for server in items]
    return [item.name for item in items]


def _none_enabled(field: str, attribute: str) -> Callable[[Context], Commission]:
    def commission(context: Context) -> Commission:
        if not _names(context.descriptor, attribute):
            raise Skip(f"the agent's Descriptor lists no {attribute}")
        return _with_settings(context, **{field: []})

    return commission


def _none_listed(attribute: str) -> Callable[[Run, Seen], list[str]]:
    def check(run: Run, seen: Seen) -> list[str]:
        started = _started(run)
        if started is None:
            return NOT_STARTED
        problems = []
        if listed := _names(started, attribute):
            problems.append(f"agent_started lists {', '.join(listed)}, which are turned off")
        if attribute == "mcp_servers":
            tools = [t.name for t in started.tools or [] if t.mcp_server_id]
            if tools:
                problems.append(f"agent_started lists {', '.join(tools)}, from turned-off servers")
        return problems

    return check


def _none_enabled_case(kind: str, field: str, attribute: str) -> Case:
    return Case(
        name=f"enabled-no-{kind}",
        rule="commission.5.2",
        level="MUST",
        about=f"An empty `{field}` means the run has no built-in {attribute}",
        commission=_none_enabled(field, attribute),
        check=_none_listed(attribute),
        responses=REPLY,
    )


def _one_tool_enabled(context: Context) -> Commission:
    tools = _names(context.descriptor, "tools")
    if not tools:
        raise Skip("the agent's Descriptor lists no tool of its own")
    return _with_settings(context, enabled_tools=tools[:1])


def _only_one_tool_listed(run: Run, seen: Seen) -> list[str]:
    started = _started(run)
    if started is None:
        return NOT_STARTED
    wanted = _names(seen.descriptor, "tools")[:1]
    listed = _names(started, "tools")
    return [] if listed == wanted else [f"agent_started lists {listed}, not only {wanted}"]


def _no_settings(context: Context) -> Commission:
    if not any(
        _names(context.descriptor, a) for a in ("tools", "mcp_servers", "skills", "subagents")
    ):
        raise Skip("the agent's Descriptor lists no built-in items")
    return _commission(context)


def _all_listed(run: Run, seen: Seen) -> list[str]:
    started = _started(run)
    if started is None:
        return NOT_STARTED
    problems = []
    for attribute in ("tools", "mcp_servers", "skills", "subagents"):
        missing = set(_names(seen.descriptor, attribute)) - set(_names(started, attribute))
        if missing:
            problems.append(f"agent_started's {attribute} leaves out {', '.join(sorted(missing))}")
    return problems


def _no_tools_enabled(context: Context) -> Commission:
    return _none_enabled("enabled_tools", "tools")(context)


def _not_offered(run: Run, seen: Seen) -> list[str]:
    if not seen.requests:
        return NO_REQUEST
    off = set(_names(seen.descriptor, "tools"))
    offered = {name for request in seen.requests for name in offered_tools(request)}
    if shown := off & offered:
        return [f"the model was offered {', '.join(sorted(shown))}, which are turned off"]
    return []


def _calls_a_built_in_tool(descriptor: AgentDescriptor) -> tuple[Response, ...]:
    tools = _names(descriptor, "tools")
    if not tools:
        return REPLY
    return (
        {"toolCalls": [{"name": tools[0], "arguments": "{}"}]},
        {"content": "A scripted reply after the tool."},
    )


def _call_was_refused(run: Run, seen: Seen) -> list[str]:
    tool = _names(seen.descriptor, "tools")[0]
    returned = [
        e for e in run.trajectory if isinstance(e, ToolReturnedEvent) and e.data.tool_name == tool
    ]
    if not returned:
        return [f"the call to {tool} has no tool_returned"]
    if returned[0].data.tool_result.is_error is not True:
        return [f"the call to {tool} ran or wasn't marked as failed: is_error isn't true"]
    return []


def _adds_a_server_and_a_skill(context: Context) -> Commission:
    server = McpServerHttp(id=SERVER_ID, type="http", url=context.mcp_url)
    return _commission(context, mcp_servers=[server], skills=[_skill(SKILL_NAME)])


def _adds_items_with_everything_off(context: Context) -> Commission:
    server = McpServerHttp(id=SERVER_ID, type="http", url=context.mcp_url)
    settings = AgentSettings(enabled_mcp_servers=[], enabled_skills=[])
    return _commission(
        context,
        mcp_servers=[server],
        skills=[_skill(SKILL_NAME)],
        agents={context.descriptor.agent_name: settings},
    )


def _server_problems(started: AgentStarted) -> list[str]:
    """The added MCP server is `connected`, and its tool is listed."""
    server = next((s for s in started.mcp_servers or [] if s.id == SERVER_ID), None)
    if server is None:
        return [f"agent_started doesn't list the MCP server {SERVER_ID}"]
    problems = []
    if server.status != "connected":
        problems.append(f"the MCP server {SERVER_ID} has the status {server.status}, not connected")
    tools = [t.name for t in started.tools or [] if t.mcp_server_id == SERVER_ID]
    if not any(TOOL_NAME in name for name in tools):
        problems.append(f"agent_started lists no tool {TOOL_NAME} from {SERVER_ID}")
    return problems


def _added_server_used(run: Run, seen: Seen) -> list[str]:
    started = _started(run)
    if started is None:
        return NOT_STARTED
    problems = _server_problems(started)
    if not seen.requests:
        return [*problems, *NO_REQUEST]
    if not any(TOOL_NAME in name for name in offered_tools(seen.requests[0])):
        problems.append(f"the model wasn't offered the tool {TOOL_NAME}")
    return problems


def _added_skill_listed(run: Run, seen: Seen) -> list[str]:
    started = _started(run)
    if started is None:
        return NOT_STARTED
    if SKILL_NAME not in _names(started, "skills"):
        return [f"agent_started doesn't list the skill {SKILL_NAME}"]
    return []


def _added_items_used(run: Run, seen: Seen) -> list[str]:
    return [*_added_server_used(run, seen), *_added_skill_listed(run, seen)]


def _has_system_prompt(context: Context) -> Commission:
    return _commission(context, system_prompt=SYSTEM_PROMPT)


def _system_prompt_replaced(run: Run, seen: Seen) -> list[str]:
    if not seen.requests:
        return NO_REQUEST
    return [
        f"the model's system prompt is {text[:200]!r}, not only the Commission's"
        for text in {system_text(request) for request in seen.requests}
        if text != SYSTEM_PROMPT
    ]


def _used_the_model(run: Run, seen: Seen) -> list[str]:
    if not seen.requests:
        return NO_REQUEST
    return [
        f"a request asked for the model {used}, not {seen.model.id}"
        for used in {model_id(request) for request in seen.requests}
        if used != seen.model.id
    ]


def _has_output_schema(context: Context) -> Commission:
    return _commission(context, output_schema=OUTPUT_SCHEMA, system_prompt=context.prompt)


def _output_rejected(run: Run, seen: Seen) -> list[str]:
    """Every response is invalid, so retries can't help."""
    codes = [e.data.error_code for e in run.trajectory if isinstance(e, ErrorOccurredEvent)]
    problems = []
    if "output_invalid" not in codes:
        problems.append(f"no error_occurred has the code output_invalid: {codes or 'none'}")
    if run.reason != "error":
        problems.append(f"agent_stopped's reason is {run.reason}, not error")
    if run.output is None:
        problems.append("agent_stopped has no output")
    return problems


def _output_matches(run: Run, seen: Seen) -> list[str]:
    """An agent that gets its output another way, such as from a tool, can reject
    this response, so that's allowed. It can't converge on output that doesn't
    match."""
    if run.reason == "converged":
        valid = isinstance(run.output, dict) and isinstance(run.output.get("answer"), str)
        return [] if valid else [f"it converged on {run.output!r}, which doesn't match the schema"]
    return _output_rejected(run, seen)


def _adds_a_server_with_a_secret(context: Context) -> Commission:
    server = McpServerHttp(
        id=SERVER_ID,
        type="http",
        url=context.mcp_url,
        headers={SECRET_HEADER: EnvSecret(env=CREDENTIAL_ENV)},
    )
    return _commission(context, mcp_servers=[server])


def _secret_kept_out(run: Run, seen: Seen) -> list[str]:
    lines = [*(e.model_dump_json() for e in run.trajectory), json.dumps(run.invalid_trajectory)]
    if any(STAND_IN in line for line in lines):
        return ["the Trajectory holds the secret's value"]
    return []


def _credential_reached_model(run: Run, seen: Seen) -> list[str]:
    if not seen.requests:
        return NO_REQUEST
    if all(has_credential(request) for request in seen.requests):
        return []
    return ["a model request has no API key"]


def _secret_reached_server(run: Run, seen: Seen) -> list[str]:
    if not seen.mcp_requests:
        return ["the agent sent its MCP server no request"]
    if any(sent_value(request, STAND_IN) for request in seen.mcp_requests):
        return []
    return [f"no MCP request's headers hold the value of {CREDENTIAL_ENV}"]


def _repeats(owner: Any, where: str) -> list[str]:
    """The names repeated in each list of a Descriptor or Subagent, and in its
    subagents' lists."""
    problems = []
    for attribute, key in (
        ("tools", "name"),
        ("mcp_servers", "id"),
        ("skills", "name"),
        ("subagents", "name"),
    ):
        items = getattr(owner, attribute, None) or []
        counts = Counter(getattr(item, key) for item in items)
        problems += [
            f"{where}'s {attribute} repeat {name}" for name, count in counts.items() if count > 1
        ]
    for subagent in getattr(owner, "subagents", None) or []:
        problems += _repeats(subagent, f"subagent {subagent.name}")
    return problems


def _names_unique(run: Run, seen: Seen) -> list[str]:
    return _repeats(seen.descriptor, "the Descriptor")


def _added_items_unlisted(run: Run, seen: Seen) -> list[str]:
    descriptor = _described(run)
    if descriptor is None:
        return ["the run has no agent_described"]
    problems = []
    if SERVER_ID in _names(descriptor, "mcp_servers"):
        problems.append(f"agent_described lists the added MCP server {SERVER_ID}")
    if SKILL_NAME in _names(descriptor, "skills"):
        problems.append(f"agent_described lists the added skill {SKILL_NAME}")
    return problems


def _has_mcp_tools(context: Context) -> Commission:
    if not any(t.mcp_server_id for t in context.descriptor.tools or []):
        raise Skip("the agent's Descriptor lists no tool from an MCP server")
    return _agents_without_entry(context)


def _dangling_servers(owner: Any, where: str) -> list[str]:
    ids = set(_names(owner, "mcp_servers"))
    problems = [
        f"{where}'s tool {tool.name} names the unknown MCP server {tool.mcp_server_id}"
        for tool in getattr(owner, "tools", None) or []
        if tool.mcp_server_id and tool.mcp_server_id not in ids
    ]
    for subagent in getattr(owner, "subagents", None) or []:
        problems += _dangling_servers(subagent, f"subagent {subagent.name}")
    return problems


def _mcp_tools_name_their_server(run: Run, seen: Seen) -> list[str]:
    return _dangling_servers(seen.descriptor, "the Descriptor")


def _connected_server_tools_listed(run: Run, seen: Seen) -> list[str]:
    """Once connected, `agent_started` lists exactly the tools the server offered."""
    started = _started(run)
    if started is None:
        return NOT_STARTED
    problems = _server_problems(started)
    tools = [t.name for t in started.tools or [] if t.mcp_server_id == SERVER_ID]
    if len(tools) != 1:
        problems.append(f"agent_started lists {tools} from {SERVER_ID}; it offered one tool")
    return problems


def _has_own_tools(context: Context) -> Commission:
    if not _names(context.descriptor, "tools"):
        raise Skip("the agent's Descriptor lists no tool of its own")
    return _commission(context)


def _tools_match(run: Run, seen: Seen) -> list[str]:
    if not seen.requests:
        return NO_REQUEST
    offered = offered_tools(seen.requests[0])
    problems = []
    for tool in seen.descriptor.tools or []:
        if tool.name not in offered:
            continue
        description, schema = offered[tool.name]
        if tool.description != description:
            problems.append(f"the model sees another description for {tool.name}")
        if schema is not None and tool.input_schema != schema:
            problems.append(f"the model sees another input schema for {tool.name}")
    return problems


def _fixed_parts(descriptor: AgentDescriptor) -> dict[str, Any]:
    """The Descriptor without what MCP servers control, with its lists in one
    order: the order is only a SHOULD."""
    fields = descriptor.model_dump(mode="json", exclude_none=True)
    fields["tools"] = [t for t in fields.get("tools", []) if not t.get("mcp_server_id")]
    for server in fields.get("mcp_servers", []):
        server.pop("status", None)
    return {
        key: sorted(value, key=json.dumps) if isinstance(value, list) else value
        for key, value in fields.items()
        if value != []
    }


def _same_descriptor(run: Run, seen: Seen) -> list[str]:
    described = _described(run)
    if described is None:
        return ["the run has no agent_described"]
    if _fixed_parts(described) != _fixed_parts(seen.descriptor):
        return ["agent_described's Descriptor differs from the answer to describe"]
    return []


def _commission_recorded(run: Run, seen: Seen) -> list[str]:
    event = next((e for e in run.trajectory if isinstance(e, RunRequestedEvent)), None)
    if event is None:
        return ["the run has no run_requested"]
    recorded = event.data.commission
    if not isinstance(recorded, Commission) or seen.sent is None:
        return ["run_requested has no Commission"]
    if recorded.model_dump(exclude_none=True) != seen.sent.model_dump(exclude_none=True):
        return ["run_requested's Commission differs from the one the agent was given"]
    return []


def _one_message_per_response(run: Run, seen: Seen) -> list[str]:
    count = len(_messages(run))
    return [] if count == 2 else [f"{count} assistant_message events for 2 model responses"]


def _message_holds_every_block(run: Run, seen: Seen) -> list[str]:
    messages = _messages(run)
    if not messages:
        return ["the run has no assistant_message"]
    content = messages[0].data.content
    problems = []
    if not any(isinstance(block, TextBlock) for block in content):
        problems.append("the first assistant_message leaves out the response's text")
    if not any(isinstance(block, ToolUseBlock) for block in content):
        problems.append("the first assistant_message leaves out the response's tool call")
    return problems


def _usage(input_tokens: int, output_tokens: int) -> Usage:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "promptTokenCount": input_tokens,
        "candidatesTokenCount": output_tokens,
    }


USAGES = ((100, 10), (40, 5))
"""The second is smaller, so running totals can't pass for per-response counts."""


def _usage_per_response(run: Run, seen: Seen) -> list[str]:
    messages = _messages(run)
    counted = [(m.data.usage.input_tokens, m.data.usage.output_tokens) for m in messages]
    problems = []
    if counted != list(USAGES):
        problems.append(f"the responses' tokens are {counted}, not {list(USAGES)}")
    for message in messages:
        usage = message.data.usage
        if (usage.cache_read_input_tokens or 0) + (
            usage.cache_creation_input_tokens or 0
        ) > usage.input_tokens:
            problems.append("cached input tokens exceed input_tokens")
        if usage.cost_source == "unknown" and usage.cost_usd != 0:
            problems.append(f"cost_source is unknown, but cost_usd is {usage.cost_usd}")
    return problems


def _failed_call_is_error(run: Run, seen: Seen) -> list[str]:
    returned = [e for e in run.trajectory if isinstance(e, ToolReturnedEvent)]
    if not returned:
        return ["the run has no tool_returned"]
    if returned[0].data.tool_result.is_error is not True:
        return ["the failed call's tool_returned doesn't have is_error set to true"]
    return []


def _failure_reported(run: Run, seen: Seen) -> list[str]:
    types = [e.type for e in run.trajectory]
    problems = []
    if "error_occurred" not in types:
        problems.append(f"no error_occurred in {', '.join(types) or 'no events'}")
    elif "agent_stopped" in types and types.index("error_occurred") > types.index("agent_stopped"):
        problems.append("error_occurred comes after agent_stopped")
    if run.reason != "error":
        problems.append(f"agent_stopped's reason is {run.reason}, not error")
    return problems


CASES: list[Case] = [
    _none_enabled_case("tools", "enabled_tools", "tools"),
    _none_enabled_case("mcp-servers", "enabled_mcp_servers", "mcp_servers"),
    _none_enabled_case("skills", "enabled_skills", "skills"),
    _none_enabled_case("subagents", "enabled_subagents", "subagents"),
    Case(
        name="enabled-one-tool",
        rule="commission.5.2",
        level="MUST",
        about="`enabled_tools` naming one tool means the run has only that one",
        commission=_one_tool_enabled,
        check=_only_one_tool_listed,
        responses=REPLY,
    ),
    Case(
        name="no-settings-allows-all",
        rule="commission.5.2",
        level="MUST",
        about="A Commission with no `agents` can use every built-in item",
        commission=_no_settings,
        check=_all_listed,
        responses=REPLY,
    ),
    Case(
        name="turned-off-tool-hidden",
        rule="commission.5.3",
        level="SHOULD",
        about="The model isn't offered a tool the Commission turns off",
        commission=_no_tools_enabled,
        check=_not_offered,
        responses=REPLY,
    ),
    Case(
        name="turned-off-tool-blocked",
        rule="commission.5.3",
        level="MUST",
        about="The model calls a tool that is turned off, so the call is recorded as failed",
        commission=_no_tools_enabled,
        check=_call_was_refused,
        responses=_calls_a_built_in_tool,
    ),
    Case(
        name="added-server-used",
        rule="commission.5.4",
        level="MUST",
        about="An added MCP server connects, and the model is offered its tools",
        commission=_adds_the_mock_mcp_server,
        check=_added_server_used,
        responses=REPLY,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="added-skill-loaded",
        rule="commission.5.4",
        level="MUST",
        about="An added skill is loaded for the run",
        commission=lambda context: _commission(context, skills=[_skill(SKILL_NAME)]),
        check=_added_skill_listed,
        responses=REPLY,
    ),
    Case(
        name="added-items-ignore-settings",
        rule="commission.5.4",
        level="MUST",
        about="Agent settings that turn everything off don't apply to added items",
        commission=_adds_items_with_everything_off,
        check=_added_items_used,
        responses=REPLY,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="system-prompt-replaces",
        rule="commission.5.5",
        level="MUST",
        about="The model's system prompt is only the Commission's `system_prompt`",
        commission=_has_system_prompt,
        check=_system_prompt_replaced,
        responses=REPLY,
    ),
    Case(
        name="run-uses-model",
        rule="commission.5.6",
        level="MUST",
        about="The agent's model calls ask for `model.id`",
        commission=_commission,
        check=_used_the_model,
        responses=REPLY,
    ),
    Case(
        name="output-mismatch-fails",
        rule="commission.5.7",
        level="MUST",
        about="Output that never matches `output_schema` ends with `output_invalid`",
        commission=_has_output_schema,
        check=_output_rejected,
        responses=tuple({"content": "This isn't JSON."} for _ in range(MANY_TURNS)),
        matches_system_prompt=True,
    ),
    Case(
        name="output-match-converges",
        rule="commission.5.7",
        level="MUST",
        about="A converged run's output matches `output_schema`",
        commission=_has_output_schema,
        check=_output_matches,
        responses=tuple({"content": '{"answer": "x"}'} for _ in range(MANY_TURNS)),
        matches_system_prompt=True,
    ),
    Case(
        name="secret-not-in-trajectory",
        rule="commission.5.8",
        level="MUST",
        about="No event holds the value of a secret the agent received",
        commission=_adds_a_server_with_a_secret,
        check=_secret_kept_out,
        responses=REPLY,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="env-credential-reaches-model",
        rule="commission.5.9",
        level="MUST",
        about="An `env` credential is sent to the model as its API key",
        commission=_commission,
        check=_credential_reached_model,
        responses=REPLY,
    ),
    Case(
        name="env-secret-reaches-mcp-server",
        rule="commission.5.9",
        level="MUST",
        about="An `env` secret's value goes to an HTTP MCP server as its header",
        commission=_adds_a_server_with_a_secret,
        check=_secret_reached_server,
        responses=REPLY,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="descriptor-names-unique",
        rule="agent-descriptor.4.1",
        level="MUST",
        about="No list in the Descriptor repeats a name or ID",
        commission=_agents_without_entry,
        check=_names_unique,
    ),
    Case(
        name="descriptor-omits-added-items",
        rule="agent-descriptor.4.2",
        level="MUST",
        about="`agent_described` doesn't list what a Commission adds",
        commission=_adds_a_server_and_a_skill,
        check=_added_items_unlisted,
        responses=REPLY,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="mcp-tools-name-their-server",
        rule="agent-descriptor.4.4",
        level="MUST",
        about="A tool's `mcp_server_id` names a server in the same list",
        commission=_has_mcp_tools,
        check=_mcp_tools_name_their_server,
    ),
    Case(
        name="connected-server-tools-listed",
        rule="agent-descriptor.4.4",
        level="MUST",
        about="A connected server has its status set and exactly its tools listed",
        commission=_adds_the_mock_mcp_server,
        check=_connected_server_tools_listed,
        responses=REPLY,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="tools-match-model",
        rule="agent-descriptor.4.5",
        level="SHOULD",
        about="A tool's description and input schema are what the model sees",
        commission=_has_own_tools,
        check=_tools_match,
        responses=REPLY,
    ),
    Case(
        name="descriptor-same-every-run",
        rule="agent-descriptor.4.6",
        level="MUST",
        about="A refused run's Descriptor is the same as the answer to `describe`",
        commission=_agents_without_entry,
        check=_same_descriptor,
    ),
    Case(
        name="run-requested-records-commission",
        rule="trajectory.4.2",
        level="MUST",
        about="`run_requested` has the Commission the agent was given",
        commission=_commission,
        check=_commission_recorded,
        responses=REPLY,
    ),
    Case(
        name="refused-run-records-commission",
        rule="trajectory.4.2",
        level="MUST",
        about="`run_requested` has the Commission even when the agent refuses it",
        commission=_agents_without_entry,
        check=_commission_recorded,
    ),
    Case(
        name="agent-described-records-descriptor",
        rule="trajectory.4.2",
        level="MUST",
        about="`agent_described` has the agent's Descriptor",
        commission=_commission,
        check=_same_descriptor,
        responses=REPLY,
    ),
    Case(
        name="agent-started-lists-added-items",
        rule="trajectory.4.2",
        level="MUST",
        about="`agent_started` lists the items a Commission adds",
        commission=_adds_a_server_and_a_skill,
        check=_added_items_used,
        responses=REPLY,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="one-message-per-response",
        rule="trajectory.4.3",
        level="MUST",
        about="Two model responses make two `assistant_message` events",
        commission=_adds_the_mock_mcp_server,
        check=_one_message_per_response,
        responses=TOOL_ROUND,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="message-holds-every-block",
        rule="trajectory.4.3",
        level="MUST",
        about="A response with text and a tool call keeps both in `content`",
        commission=_adds_the_mock_mcp_server,
        check=_message_holds_every_block,
        responses=(
            {"content": "Scripted text before the tool.", "toolCalls": [CALLS_THE_TOOL]},
            {"content": "A scripted reply after the tool."},
        ),
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="usage-per-response",
        rule="trajectory.4.4",
        level="MUST",
        about="Each `assistant_message`'s usage counts only that response",
        commission=_adds_the_mock_mcp_server,
        check=_usage_per_response,
        responses=(
            {"toolCalls": [CALLS_THE_TOOL], "usage": _usage(*USAGES[0])},
            {"content": "A scripted reply after the tool.", "usage": _usage(*USAGES[1])},
        ),
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="tool-call-has-result",
        rule="trajectory.4.5",
        level="MUST",
        about="A model's tool call gets a `tool_invoked`, then a `tool_returned`",
        commission=_adds_the_mock_mcp_server,
        check=_every_tool_call_has_a_result,
        responses=TOOL_ROUND,
        mcp_tools=OFFERS_A_TOOL,
    ),
    Case(
        name="failed-tool-call-is-error",
        rule="trajectory.4.5",
        level="MUST",
        about="A failed tool call's `tool_returned` has `is_error` set to true",
        commission=_adds_the_mock_mcp_server,
        check=_failed_call_is_error,
        responses=TOOL_ROUND,
        mcp_tools=({"name": TOOL_NAME, "error": "A scripted tool failure."},),
    ),
    Case(
        name="failed-run-stops-with-error",
        rule="trajectory.4.7",
        level="MUST",
        about="A model error ends with `error_occurred`, then `agent_stopped` with `error`",
        commission=_commission,
        check=_failure_reported,
        responses=(
            {
                "error": {"message": "A scripted failure.", "type": "invalid_request_error"},
                "status": 400,
            },
        ),
    ),
    Case(
        name="events-in-order",
        rule="trajectory.4.1",
        level="MUST",
        about="A run with one model response sends its events in the fixed order",
        commission=_commission,
        check=_events_in_order,
        responses=({"content": "A scripted reply."},),
    ),
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

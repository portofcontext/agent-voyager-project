"""AVP event emitters for the Claude Agent SDK adapter.

Currently covers the prelude only (`run_requested`, `agent_described`,
`agent_started`); per-message handlers and turn lifecycle are
reintroduced incrementally.
"""

from __future__ import annotations

import json
import time
from typing import Any

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    McpStatusResponse,
    Message,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUsage,
    ToolResultBlock,
    UserMessage,
)

from avp.commission import Commission
from avp.content import AVPContentBlock
from avp.content import ServerToolResultBlock as AVPServerToolResultBlock
from avp.content import ServerToolUseBlock as AVPServerToolUseBlock
from avp.content import ToolResultBlock as AVPToolResultBlock
from avp.content import ToolUseBlock as AVPToolUseBlock
from avp.descriptor import ToolDecl
from avp.envelope import ZERO_SPAN_ID, new_span_id
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    ErrorCode,
    ErrorOccurredData,
    ErrorOccurredEvent,
    RunRequestedData,
    RunRequestedEvent,
    StopReason,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    SubagentUsage,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
)
from avp_claude_agent_sdk._runstate import RunState, TaskInfo, ToolSpan, Turn
from avp_claude_agent_sdk._translator import (
    get_dispatch_target,
    mcp_servers_from_status,
    request_model_from_init,
    resolve_system_prompt,
    skills_from_init,
    subagents_from_init,
    tools_from_init,
    translate_agent_descriptor,
    translate_content_blocks,
    translate_usage,
)

_PROVIDER_NAME = "anthropic"


async def emit_run_requested(state: RunState, commission: Commission | None = None) -> None:
    """First event of the trajectory. Anchors the run.

    Stamps `avp.supervisor.{name,version}` from `Commission.supervisor` for
    attribution (spec §2.1), matching the avp-goose connector; left unset when
    the Commission carries no supervisor.
    """
    supervisor = commission.supervisor if commission else None
    await state.sink(
        RunRequestedEvent(
            subject=state.run_id,
            data=RunRequestedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                supervisor_name=supervisor.name if supervisor else None,
                supervisor_version=supervisor.version if supervisor else None,
                commission=commission,
            ),
        )
    )


async def emit_agent_described(
    state: RunState,
    options: ClaudeAgentOptions,
    *,
    prompt: str | None,
    init_data: dict[str, Any] | None,
    status: McpStatusResponse,
) -> None:
    """Pre-Commission capability surface (probe-derived descriptor).

    `init_data` from a probe `SystemMessage(init)`; `status` from the
    probe's `get_mcp_status()`. When `init_data is None`, the descriptor
    carries identity + default_model only -- still spec-conformant.
    """
    await state.sink(
        AgentDescribedEvent(
            subject=state.run_id,
            data=AgentDescribedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                descriptor=translate_agent_descriptor(options, init_data, status, prompt=prompt),
            ),
        )
    )


def _apply_enabled_builtin_tools(
    tools: list[ToolDecl] | None, allow: list[str] | None
) -> list[ToolDecl] | None:
    """Apply the Commission's `enabled_builtin_tools` allow-list to the merged
    `agent_started` tool bag. `None` (no allow-list) exposes all and is passed
    through unchanged; any concrete list keeps only the named tools, so `[]`
    yields `[]` (none) even when the CLI reported no tools section. This is the
    spec's subtractive filter over `descriptor.tools` (which, for claude, is the
    single bag of built-in AND MCP-surfaced tools)."""
    if allow is None:
        return tools
    allowed = set(allow)
    return [t for t in (tools or []) if t.name in allowed]


# Context-usage keys worth carrying on the wire: the ones that attribute the
# run's fixed input-token cost (system prompt, tool catalog, skills, memory)
# and the window they fit in. gridRows (visual rendering), apiUsage, and
# slashCommands stay behind.
_CONTEXT_USAGE_KEYS = (
    "totalTokens",
    "maxTokens",
    "rawMaxTokens",
    "percentage",
    "model",
    "categories",
    "systemPromptSections",
    "systemTools",
    "deferredBuiltinTools",
    "mcpTools",
    "memoryFiles",
    "skills",
    "agents",
    "isAutoCompactEnabled",
    "autoCompactThreshold",
)


async def context_usage_meta(client: ClaudeSDKClient) -> dict[str, Any] | None:
    """Token attribution for the run's starting context, from the SDK's
    `get_context_usage()` (the `/context` breakdown): how many tokens the
    system prompt, built-in tool catalog, per-server MCP tools, skill
    frontmatter, and memory files each consume. This is the measurable
    answer to "what does the model see on turn 1" for a CLI that doesn't
    expose its catalog text; rides as opaque annotations under `avp.meta`
    (spec §2). Returns None when the control request is unsupported or
    fails (older CLI builds): the prelude must not depend on it."""
    try:
        usage: dict[str, Any] = dict(await client.get_context_usage())
    except Exception:
        return None
    trimmed = {k: usage[k] for k in _CONTEXT_USAGE_KEYS if usage.get(k) not in (None, [], {})}
    return trimmed or None


async def emit_agent_started(
    state: RunState,
    *,
    prompt: str | None,
    options: ClaudeAgentOptions,
    init_data: dict[str, Any] | None,
    status: McpStatusResponse,
    context_usage: dict[str, Any] | None = None,
) -> None:
    """Merged-state snapshot for the run. Sets `state.agent_span_id` so
    subsequent turn / tool events parent under it."""
    agent_span_id = new_span_id()
    state.agent_span_id = agent_span_id
    sdk_session_id = init_data.get("session_id") if init_data else None
    meta: dict[str, Any] = {}
    if sdk_session_id:
        meta["claude_agent_sdk.session_id"] = sdk_session_id
    if context_usage:
        meta["claude_agent_sdk.context_usage"] = context_usage
    await state.sink(
        AgentStartedEvent(
            subject=state.run_id,
            data=AgentStartedData(
                trace_id=state.trace_id,
                span_id=agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                meta=meta or None,
                provider_name=_PROVIDER_NAME,
                operation_name="invoke_agent",
                request_model=(
                    request_model_from_init(init_data, options) if init_data else options.model
                ),
                prompt=prompt,
                system_prompt=resolve_system_prompt(options.system_prompt),
                tools=_apply_enabled_builtin_tools(
                    tools_from_init(init_data, status) if init_data else None,
                    state.enabled_builtin_tools,
                ),
                mcp_servers=mcp_servers_from_status(status),
                skills=skills_from_init(init_data) if init_data else None,
                subagents=subagents_from_init(init_data) if init_data else None,
            ),
        )
    )


async def emit_agent_stopped(
    state: RunState,
    reason: StopReason,
    *,
    output: Any = None,
) -> None:
    """Final event of the trajectory. Idempotent via `state.stopped` so
    ResultMessage handling, disconnect fallbacks, and exception paths
    can all call this safely without double-emitting. Drains any open
    turn first so the last `assistant_message` lands before the close
    regardless of which path triggered the stop."""
    if state.stopped:
        return
    if state.agent_span_id is not None:
        await state.drain()
    state.stopped = True
    await state.sink(
        AgentStoppedEvent(
            subject=state.run_id,
            data=AgentStoppedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=state.agent_span_id or ZERO_SPAN_ID,
                reason=reason,
                output=output,
            ),
        )
    )


async def emit_error(
    state: RunState, exc: Exception, error_code: ErrorCode = ErrorCode.agent_crash
) -> None:
    """Emit `error_occurred`. Parents under the agent span once the loop has
    started, else the root (a pre-loop fail-fast has no agent frame yet)."""
    await state.sink(
        ErrorOccurredEvent(
            subject=state.run_id,
            data=ErrorOccurredData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=state.agent_span_id or ZERO_SPAN_ID,
                error_code=error_code,
                error_message=str(exc) or type(exc).__name__,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Per-message handlers
# ---------------------------------------------------------------------------


async def _on_system_init(client: ClaudeSDKClient, state: RunState, message: SystemMessage) -> None:
    """Emit `agent_started` on the real session's first `init` SystemMessage.

    Skips non-`init` subtypes (e.g. `compact_boundary`). Uses init_data from
    the *real* session (not the probe's) so the merged snapshot reflects
    what the run will actually use.
    """
    if message.subtype != "init":
        return
    status = await client.get_mcp_status()
    context_usage = await context_usage_meta(client)
    await emit_agent_started(
        state,
        prompt=state.prompt,
        options=client.options,
        init_data=message.data,
        status=status,
        context_usage=context_usage,
    )


async def _on_assistant(state: RunState, message: AssistantMessage) -> None:
    """Handle one AssistantMessage chunk.

    Drains the open turn on a new `message_id`, then opens (if needed)
    and extends the current turn with the chunk's content, model,
    stop_reason, and usage. Emits `tool_invoked` for each `ToolUseBlock`
    (including Task dispatches: per spec §5, the subagent_* events layer
    on top of the tool dispatch, they don't replace it) and
    `ServerToolUseBlock`, plus `tool_returned` for each
    `ServerToolResultBlock` (server tools complete inline in the same
    response). Subagent-interior chunks (`parent_tool_use_id is not
    None`) are skipped under the in-process subagent fallback (spec §5.6)."""
    if message.parent_tool_use_id is not None:
        return

    # The Claude CLI fans one API response's content blocks out as one
    # AssistantMessage per block, all stamped with the same `message_id`.
    # One AVP turn = one inference = one `message_id`, so multiple SDK
    # chunks merge into the open turn; a different non-None `message_id`
    # is the boundary that closes the prior inference.
    # Close the prior inference when a new one begins: a different non-None
    # message_id, OR a turn already marked `tool_resulted` (its inference ended
    # at the tool call, so this message starts a fresh one even if it shares or
    # lacks a message_id). Chunks of one inference (same message_id, no tool
    # result yet) merge into the open turn.
    if state.turn is not None and (
        state.turn.tool_resulted
        or (message.message_id is not None and message.message_id != state.turn.message_id)
    ):
        await state.drain()

    if state.turn is None:
        state.turn = Turn(message_id=message.message_id, step=state.last_step + 1)

    state.turn.meta_chunks_merged += 1
    translated = translate_content_blocks(message.content)
    state.turn.content.extend(translated)
    for block in translated:
        if isinstance(block, AVPToolUseBlock | AVPServerToolUseBlock):
            _buffer_tool_invoked(state, block.id, block.name, block.input)
        elif isinstance(block, AVPServerToolResultBlock):
            # Server tools execute in the model's runtime and return
            # inline in the same response, so bracket within this chunk.
            _buffer_tool_returned(
                state,
                block.tool_use_id,
                AVPToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    content=_normalize_tool_result_content(block.content),
                ),
            )

    if state.turn.response_model is None:
        state.turn.response_model = message.model
    if message.stop_reason:
        state.turn.stop_reason = message.stop_reason
    if message.usage:
        state.turn.usage = translate_usage(message.usage)
        state.turn.meta_service_tier = (
            message.usage.get("service_tier") or state.turn.meta_service_tier
        )
        cache_creation = message.usage.get("cache_creation") or {}
        if isinstance(cache_creation, dict):
            state.turn.meta_cache_creation_5m = int(
                cache_creation.get("ephemeral_5m_input_tokens") or 0
            )
            state.turn.meta_cache_creation_1h = int(
                cache_creation.get("ephemeral_1h_input_tokens") or 0
            )


def _buffer_tool_invoked(
    state: RunState,
    tool_use_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> None:
    """Mint a span, register a `ToolSpan` for later pairing, and append
    a `tool_invoked` to the open turn's emissions. No-op if no turn open.
    """
    if state.turn is None:
        return
    span_id = new_span_id()
    state.turn.tool_spans[tool_use_id] = ToolSpan(
        span_id=span_id,
        step=state.turn.step,
        name=tool_name,
        started_at=time.monotonic(),
    )
    state.turn.emissions.append(
        ToolInvokedEvent(
            subject=state.run_id,
            data=ToolInvokedData(
                trace_id=state.trace_id,
                span_id=span_id,
                parent_span_id=state.turn.span_id,
                step=state.turn.step,
                tool_call_id=tool_use_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_dispatch_target=get_dispatch_target(tool_name),
            ),
        )
    )


def _buffer_tool_returned(
    state: RunState,
    tool_use_id: str,
    tool_result: AVPToolResultBlock,
) -> None:
    """Pop the matching `ToolSpan` and append a paired `tool_returned`
    to the open turn's emissions. Silently drops if no matching
    invocation: unknown ids or no open turn."""
    if state.turn is None:
        return
    span = state.turn.tool_spans.pop(tool_use_id, None)
    if span is None:
        return
    duration_ms = max(0, int((time.monotonic() - span.started_at) * 1000))
    state.turn.emissions.append(
        ToolReturnedEvent(
            subject=state.run_id,
            data=ToolReturnedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=span.span_id,
                step=span.step,
                tool_call_id=tool_use_id,
                tool_name=span.name,
                duration_ms=duration_ms,
                tool_result=tool_result,
            ),
        )
    )


def _normalize_tool_result_content(content: Any) -> str | list[Any]:
    """Coerce arbitrary tool-result payloads into AVP `ToolResultBlock.content`.

    Strings pass through; `None` becomes `""`; anything else is
    JSON-encoded (or stringified as a last resort) so the AVP block
    validates while preserving the payload lossily-but-observably."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except (TypeError, ValueError):
        return str(content)


async def _on_user(state: RunState, message: UserMessage) -> None:
    """Handle one UserMessage: each `ToolResultBlock` in `content` closes
    a prior `tool_invoked`. Subagent-interior UserMessages are skipped.
    Per spec §5, subagent dispatches close their tool-dispatch span here
    just like any other tool call; the `subagent_*` events are layered
    on top via `_on_task_*`, they don't replace the tool pair."""
    if message.parent_tool_use_id is not None:
        return
    if state.turn is None:
        return
    content = message.content if isinstance(message.content, list) else []
    tool_results = [b for b in content if isinstance(b, ToolResultBlock)]
    if not tool_results:
        return
    # `UserMessage.tool_use_result` is the SDK's structured-payload
    # channel paired with the human-readable `ToolResultBlock.content`
    # string. It's per-message, so attribution is only unambiguous when
    # there's exactly one result block; multi-result messages drop it
    # to avoid mis-attribution. Wrap non-dict payloads so the AVP field
    # still validates.
    structured: dict[str, Any] | None
    if len(tool_results) == 1 and message.tool_use_result is not None:
        raw = message.tool_use_result
        structured = raw if isinstance(raw, dict) else {"result": raw}
    else:
        structured = None
    for block in tool_results:
        _buffer_tool_returned(
            state,
            block.tool_use_id,
            AVPToolResultBlock(
                tool_use_id=block.tool_use_id,
                content=_normalize_tool_result_content(block.content),
                structured_content=structured,
                is_error=block.is_error,
            ),
        )
    # The tool result ends this inference; the next AssistantMessage opens a new
    # turn. Drain stays deferred to that message so parallel results spanning
    # several UserMessages all attach to this turn first.
    state.turn.tool_resulted = True


# ---------------------------------------------------------------------------
# Subagent (Task) lifecycle
# ---------------------------------------------------------------------------


_TASK_STATUS_TO_REASON: dict[str, StopReason] = {
    "completed": StopReason.converged,
    "stopped": StopReason.interrupted,
    "failed": StopReason.error,
}


def _task_usage_to_subagent_usage(usage: TaskUsage | None) -> SubagentUsage | None:
    """Project a `TaskUsage` onto AVP `SubagentUsage`.

    `TaskUsage` carries `{total_tokens, tool_uses, duration_ms}` with no
    input/output split or cost. AVP required fields stay at 0 (honest
    sentinel -- we don't know); the raw triple rides along as extras
    (`SubagentUsage` permits open keys).
    """
    if not usage:
        return None
    return SubagentUsage(
        cost_usd=0.0,
        tokens_input=0,
        tokens_output=0,
        turns=0,
        total_tokens=int(usage.get("total_tokens") or 0),
        tool_uses=int(usage.get("tool_uses") or 0),
        duration_ms=int(usage.get("duration_ms") or 0),
    )


def _subagent_input(state_turn_content: list[AVPContentBlock], tool_use_id: str) -> dict[str, Any]:
    """Find the parent's Task `ToolUseBlock` in the open turn's content
    and return its input dict (the subagent's prompt / subagent_type /
    description). Empty dict if not found (defensive)."""
    for block in state_turn_content:
        if isinstance(block, AVPToolUseBlock) and block.id == tool_use_id:
            return block.input
    return {}


async def _on_task_started(state: RunState, message: TaskStartedMessage) -> None:
    """Buffer a `subagent_invoked` onto the open turn's emissions.

    Fires when the CLI spawns a Task subagent. We record the dispatch
    in `state.turn.tasks` for `_on_task_notification` to pair against.
    The matching `ToolUseBlock` (in `state.turn.content`) supplies
    `subagent_input`. Per spec §5, the subagent frame parents under
    the enclosing turn span (sibling of `tool_invoked`, not nested
    under it): the tool pair and the subagent pair are parallel views
    of the same call.
    """
    if state.turn is None or not message.tool_use_id:
        return
    span_id = new_span_id()
    task_type = message.task_type or "Task"
    state.turn.tasks[message.tool_use_id] = TaskInfo(
        span_id=span_id,
        parent_span_id=state.turn.span_id,
        step=state.turn.step,
        task_type=task_type,
        started_at=time.monotonic(),
    )
    state.turn.emissions.append(
        SubagentInvokedEvent(
            subject=state.run_id,
            data=SubagentInvokedData(
                trace_id=state.trace_id,
                span_id=span_id,
                parent_span_id=state.turn.span_id,
                step=state.turn.step,
                subagent_name=task_type,
                subagent_invocation_id=message.tool_use_id,
                subagent_input=_subagent_input(state.turn.content, message.tool_use_id),
            ),
        )
    )


async def _on_task_notification(state: RunState, message: TaskNotificationMessage) -> None:
    """Buffer the matching `subagent_returned` onto the open turn's
    emissions. Status maps to `avp.subagent.reason`: completed→converged,
    stopped→interrupted, failed→error (with `result.text` carrying the
    failure summary). No-op if the dispatch wasn't recorded (e.g. the
    parent turn drained early)."""
    if state.turn is None or not message.tool_use_id:
        return
    info = state.turn.tasks.pop(message.tool_use_id, None)
    if info is None:
        return
    duration_ms = max(0, int((time.monotonic() - info.started_at) * 1000))
    summary = message.summary or ""
    reason = _TASK_STATUS_TO_REASON.get(message.status, StopReason.converged)
    state.turn.emissions.append(
        SubagentReturnedEvent(
            subject=state.run_id,
            data=SubagentReturnedData(
                trace_id=state.trace_id,
                # span_id matches subagent_invoked (same frame, closed).
                span_id=info.span_id,
                # Parent under the turn span (per spec §5: subagent frame
                # is a sibling of `tool_invoked`, not nested under it).
                parent_span_id=info.parent_span_id,
                step=info.step,
                subagent_name=info.task_type,
                subagent_invocation_id=message.tool_use_id,
                duration_ms=duration_ms,
                subagent_result_text=summary,
                subagent_reason=reason,
                subagent_usage=_task_usage_to_subagent_usage(message.usage),
            ),
        )
    )


async def _on_result(state: RunState, message: ResultMessage) -> None:
    """Map `ResultMessage` to `agent_stopped`. The wire message carries
    the stop info (`is_error`, `stop_reason`, `result`); only this path
    can distinguish converged / error / refused. `emit_agent_stopped` is
    idempotent via `state.stopped`, so the `_client.py` disconnect /
    exception paths remain safe fallbacks for premature termination."""
    if message.is_error:
        reason = StopReason.error
    elif message.stop_reason == "refusal":
        reason = StopReason.refused
    else:
        reason = StopReason.converged
    await emit_agent_stopped(state, reason, output=message.result)


# ---------------------------------------------------------------------------
# Public dispatch entry point
# ---------------------------------------------------------------------------


async def handle_message(client: ClaudeSDKClient, state: RunState, message: Message) -> None:
    """Dispatch one SDK message to the appropriate AVP emitter. Mutates state."""
    # Task* messages subclass SystemMessage in the SDK, so the subclass
    # branches MUST come before the generic SystemMessage branch.
    if isinstance(message, TaskStartedMessage):
        await _on_task_started(state, message)
    elif isinstance(message, TaskNotificationMessage):
        await _on_task_notification(state, message)
    elif isinstance(message, SystemMessage):
        await _on_system_init(client, state, message)
    elif isinstance(message, AssistantMessage):
        await _on_assistant(state, message)
    elif isinstance(message, UserMessage):
        await _on_user(state, message)
    elif isinstance(message, ResultMessage):
        await _on_result(state, message)
    # TaskProgressMessage, MirrorErrorMessage, StreamEvent, RateLimitEvent:
    # drop. Honest-silent beats fabricated events.

"""Claude Agent SDK message handlers: SDK messages in, Recorder calls out.

Everything harness-specific lives here (which SDK message means what, the
probe-derived descriptor, Anthropic usage extras, stop-reason inference);
the trajectory's ordering and span rules live in `avp.recorder.Recorder`.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    McpStatusResponse,
    Message,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUsage,
    TextBlock,
    ToolResultBlock,
    UserMessage,
)

from avp.commission import Commission
from avp.descriptor import SkillDecl, SubagentDecl, ToolDecl
from avp.trajectory import ErrorCode, StopReason, SubagentUsage
from avp_claude_agent_sdk._runstate import RunState
from avp_claude_agent_sdk._translator import (
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


async def emit_prelude(
    state: RunState,
    options: ClaudeAgentOptions,
    *,
    commission: Commission | None,
    prompt: str | None,
    init_data: dict[str, Any] | None,
    status: McpStatusResponse,
) -> None:
    """`run_requested` then `agent_described` (the pre-Commission capability
    surface from the probe session).

    `init_data` from a probe `SystemMessage(init)`; `status` from the
    probe's `get_mcp_status()`. When `init_data is None`, the descriptor
    carries identity + default_model only -- still spec-conformant.
    """
    await state.rec.prelude(
        commission, translate_agent_descriptor(options, init_data, status, prompt=prompt)
    )


_Decl = TypeVar("_Decl", ToolDecl, SubagentDecl, SkillDecl)


def _apply_allow_list(decls: list[_Decl] | None, allow: list[str] | None) -> list[_Decl] | None:
    """Apply a Commission allow-list to the merged `agent_started` view.
    `None` (no allow-list) exposes all and is passed through unchanged; any
    concrete list keeps only the named entries, so `[]` yields `[]` (none) even
    when the CLI reported no such section. This is the spec's subtractive
    filter over the descriptor (whose tools, for claude, are the single bag of
    built-in AND MCP-surfaced tools)."""
    if allow is None:
        return decls
    allowed = set(allow)
    return [d for d in (decls or []) if d.name in allowed]


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
    """Merged-state snapshot for the run (`agent_started`)."""
    sdk_session_id = init_data.get("session_id") if init_data else None
    meta: dict[str, Any] = {}
    if sdk_session_id:
        meta["claude_agent_sdk.session_id"] = sdk_session_id
    if context_usage:
        meta["claude_agent_sdk.context_usage"] = context_usage
    await state.rec.start(
        request_model=request_model_from_init(init_data, options) if init_data else options.model,
        prompt=prompt if isinstance(prompt, str) or prompt is None else None,
        system_prompt=resolve_system_prompt(options.system_prompt),
        tools=_apply_allow_list(
            tools_from_init(init_data, status, state.catalog) if init_data else None,
            state.enabled_builtin_tools,
        ),
        mcp_servers=mcp_servers_from_status(status),
        skills=_apply_allow_list(
            skills_from_init(init_data, state.catalog) if init_data else None, state.skills_filter
        ),
        subagents=_apply_allow_list(
            subagents_from_init(init_data, state.catalog) if init_data else None,
            state.enabled_builtin_subagents,
        ),
        meta=meta,
    )


async def emit_agent_stopped(state: RunState, reason: StopReason, *, output: Any = None) -> None:
    """Final event of the trajectory. Idempotent, so ResultMessage handling,
    disconnect fallbacks, and exception paths can all call it.

    A subagent still running at this point is closed as `abandoned` and a
    `converged` stop downgrades to match: the SDK's `ResultMessage` says
    `success` when a parent stops before its background child reports."""
    if not state.stopped:
        await _release_results(state)
        for message in list(state.finished_tasks.values()):
            await _close_task(state, message)
    await state.rec.stop(reason, output)


async def emit_error(
    state: RunState, exc: Exception, error_code: ErrorCode = ErrorCode.agent_crash
) -> None:
    await state.rec.error(error_code, str(exc) or type(exc).__name__)


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
        prompt=state.prompt,  # type: ignore[arg-type]
        options=client.options,
        init_data=message.data,
        status=status,
        context_usage=context_usage,
    )


# The CLI reports a failed API call as a synthetic AssistantMessage whose text
# is the error ("Invalid API key · ..."), flagged with `error`. It is a
# failure, not model output.
_ASSISTANT_ERROR_CODES: dict[str, ErrorCode] = {
    "authentication_failed": ErrorCode.auth_error,
    "billing_error": ErrorCode.rate_limit,
    "rate_limit": ErrorCode.rate_limit,
    "server_error": ErrorCode.agent_crash,
}


async def _on_assistant(state: RunState, message: AssistantMessage) -> None:
    """Report one AssistantMessage chunk. Chunks of one API response share a
    `message_id`, which becomes the turn key. Subagent-interior chunks
    (`parent_tool_use_id is not None`) are skipped under the in-process
    subagent fallback (spec §5.6). A message flagged with `error` is the
    CLI's rendering of a failed API call and is reported as `error_occurred`;
    the `ResultMessage` that follows stops the run as `error`."""
    if message.parent_tool_use_id is not None:
        return
    if message.error is not None:
        text = " ".join(b.text for b in message.content if isinstance(b, TextBlock)).strip()
        await state.rec.error(
            _ASSISTANT_ERROR_CODES.get(message.error, ErrorCode.unknown), text or message.error
        )
        return
    if message.message_id and message.message_id != state.turn_key:
        # A new response: whatever the previous one called has run.
        await _release_results(state)
    state.turn_key = message.message_id or state.turn_key or "anonymous"
    meta: dict[str, Any] = {"anthropic.message_id": message.message_id or None}
    if message.usage:
        if message.usage.get("service_tier"):
            meta["anthropic.service_tier"] = message.usage["service_tier"]
        cache_creation = message.usage.get("cache_creation") or {}
        if isinstance(cache_creation, dict):
            meta["anthropic.cache_creation.ephemeral_5m_input_tokens"] = int(
                cache_creation.get("ephemeral_5m_input_tokens") or 0
            )
            meta["anthropic.cache_creation.ephemeral_1h_input_tokens"] = int(
                cache_creation.get("ephemeral_1h_input_tokens") or 0
            )
    if message.usage:
        state.turn_usage = dict(message.usage)
    await state.rec.assistant(
        translate_content_blocks(message.content),
        translate_usage(message.usage) if message.usage else None,
        model=message.model,
        turn_key=state.turn_key,
        finish_reasons=[message.stop_reason] if message.stop_reason else None,
        meta={k: v for k, v in meta.items() if v is not None},
    )


async def _on_stream_event(state: RunState, message: StreamEvent) -> None:
    """Track the main-thread response's stream and complete its turn's usage.

    The CLI stamps each AssistantMessage with the `message_start` usage, whose
    `output_tokens` is a placeholder; the final, cumulative counts arrive in
    `message_delta`. Tool results held while the response streamed are
    reported at `message_stop`, once the turn holds every call and its usage."""
    event = message.event
    if message.parent_tool_use_id is not None:
        return
    kind = event.get("type")
    if kind == "message_start":
        state.streaming = True
        return
    if kind == "message_stop":
        state.streaming = False
        await _release_results(state)
        return
    if kind != "message_delta" or state.turn_usage is None:
        return
    delta = {k: v for k, v in (event.get("usage") or {}).items() if v is not None}
    state.turn_usage = {**state.turn_usage, **delta}
    await state.rec.assistant([], translate_usage(state.turn_usage), turn_key=state.turn_key)


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
    """Each `ToolResultBlock` in a UserMessage closes a prior tool call.
    Subagent-interior UserMessages are skipped. A result that arrives while
    its response is still streaming is held until the response completes
    (see `RunState.streaming`), so the turn carries all of its calls."""
    if message.parent_tool_use_id is not None:
        return
    content = message.content if isinstance(message.content, list) else []
    if state.streaming and any(isinstance(b, ToolResultBlock) for b in content):
        state.held_results.append(message)
        return
    await _report_results(state, message)


async def _release_results(state: RunState) -> None:
    """Report the tool results held for the response that just completed."""
    held, state.held_results = state.held_results, []
    for message in held:
        await _report_results(state, message)


async def _report_results(state: RunState, message: UserMessage) -> None:
    """Per spec §5, subagent dispatches close their tool-dispatch span here
    like any other call; the `subagent_*` events layer on top via
    `_on_task_*`."""
    content = message.content if isinstance(message.content, list) else []
    tool_results = [b for b in content if isinstance(b, ToolResultBlock)]
    if tool_results:
        state.turn_usage = None
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
        state.answered_calls.add(block.tool_use_id)
        finished = state.finished_tasks.get(block.tool_use_id)
        if finished is not None:
            await _close_task(state, finished, structured)
        await state.rec.tool_result(
            block.tool_use_id,
            _normalize_tool_result_content(block.content),
            is_error=bool(block.is_error),
            structured_content=structured,
        )


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
    input/output split or cost, so `cost_usd` / `tokens_input` /
    `tokens_output` / `turns` cannot be filled from it.

    We omit them rather than zero-filling. A 0 is indistinguishable from a
    measured zero, so a consumer summing `cost_usd` across a run would
    silently under-report every delegated inference and never know it. Per
    spec §2.1 absence is the signal for "not reported"; the raw triple rides
    along as extras (`SubagentUsage` permits open keys).
    """
    if not usage:
        return None
    return SubagentUsage(
        total_tokens=int(usage.get("total_tokens") or 0),
        tool_uses=int(usage.get("tool_uses") or 0),
        duration_ms=int(usage.get("duration_ms") or 0),
    )


async def _on_task_started(state: RunState, message: TaskStartedMessage) -> None:
    """Open a subagent frame when the CLI spawns a Task subagent. The frame
    takes its turn and input from the `Agent` tool call with the same id."""
    if not message.tool_use_id:
        return
    await state.rec.subagent_start(message.tool_use_id, message.task_type or "Task")


async def _on_task_notification(state: RunState, message: TaskNotificationMessage) -> None:
    """A subagent finished. The notification arrives before the `Agent` tool
    result, whose payload carries the child's final usage and answer, so the
    frame closes there. A background subagent's tool result came back at
    launch, so its frame closes here. A subagent that never reports is closed
    as `abandoned` at stop."""
    if not message.tool_use_id:
        return
    if message.tool_use_id in state.answered_calls:
        await _close_task(state, message)
    else:
        state.finished_tasks[message.tool_use_id] = message


def _agent_result_usage(result: dict[str, Any]) -> SubagentUsage | None:
    """The `Agent` tool result's final usage, split like a turn's. `TaskUsage`
    totals are taken before the child's last response completes."""
    usage = result.get("usage")
    if not isinstance(usage, dict):
        return None
    split = translate_usage(usage)
    return SubagentUsage(
        tokens_input=split.input_tokens,
        tokens_output=split.output_tokens,
        total_tokens=result.get("totalTokens"),
        tool_uses=result.get("totalToolUseCount"),
        duration_ms=result.get("totalDurationMs"),
    )


async def _close_task(
    state: RunState, message: TaskNotificationMessage, result: dict[str, Any] | None = None
) -> None:
    """Close the subagent frame. Status maps to `avp.subagent.reason`:
    completed→converged, stopped→interrupted, failed→error (with the summary
    carrying the failure)."""
    state.finished_tasks.pop(message.tool_use_id, None)
    usage = _agent_result_usage(result) if result else None
    blocks = (result or {}).get("content")
    text = (
        "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        if isinstance(blocks, list)
        else None
    )
    await state.rec.subagent_result(
        message.tool_use_id,
        text or message.summary or "",
        _TASK_STATUS_TO_REASON.get(message.status, StopReason.converged),
        usage=usage or _task_usage_to_subagent_usage(message.usage),
    )


async def _on_result(state: RunState, message: ResultMessage) -> None:
    """Map `ResultMessage` to `agent_stopped`. The wire message carries
    the stop info (`is_error`, `stop_reason`, `result`); only this path
    can distinguish converged / error / refused. Stop is idempotent, so the
    `_client.py` disconnect / exception paths remain safe fallbacks for
    premature termination."""
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
    """Dispatch one SDK message to the appropriate handler."""
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
    elif isinstance(message, StreamEvent):
        await _on_stream_event(state, message)
    # TaskProgressMessage, MirrorErrorMessage, RateLimitEvent: drop.
    # Honest-silent beats fabricated events.

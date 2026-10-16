"""Claude Agent SDK message handlers: SDK messages in, Recorder calls out.

Everything harness-specific lives here (which SDK message means what, the
probe-derived descriptor, Anthropic usage extras, stop-reason inference);
the trajectory's ordering and span rules live in `avp.recorder.Recorder`.
"""

from __future__ import annotations

import json
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
from avp.descriptor import ToolDecl
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
        tools=_apply_enabled_builtin_tools(
            tools_from_init(init_data, status) if init_data else None,
            state.enabled_builtin_tools,
        ),
        mcp_servers=mcp_servers_from_status(status),
        skills=skills_from_init(init_data) if init_data else None,
        subagents=subagents_from_init(init_data) if init_data else None,
        meta=meta,
    )


async def emit_agent_stopped(state: RunState, reason: StopReason, *, output: Any = None) -> None:
    """Final event of the trajectory. Idempotent, so ResultMessage handling,
    disconnect fallbacks, and exception paths can all call it.

    A subagent still running at this point is closed as `abandoned` and a
    `converged` stop downgrades to match: the SDK's `ResultMessage` says
    `success` when a parent stops before its background child reports."""
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


async def _on_assistant(state: RunState, message: AssistantMessage) -> None:
    """Report one AssistantMessage chunk. Chunks of one API response share a
    `message_id`, which becomes the turn key. Subagent-interior chunks
    (`parent_tool_use_id is not None`) are skipped under the in-process
    subagent fallback (spec §5.6)."""
    if message.parent_tool_use_id is not None:
        return
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
    await state.rec.assistant(
        translate_content_blocks(message.content),
        translate_usage(message.usage) if message.usage else None,
        model=message.model,
        turn_key=state.turn_key,
        finish_reasons=[message.stop_reason] if message.stop_reason else None,
        meta={k: v for k, v in meta.items() if v is not None},
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
    """Each `ToolResultBlock` in a UserMessage closes a prior tool call.
    Subagent-interior UserMessages are skipped. Per spec §5, subagent
    dispatches close their tool-dispatch span here like any other call; the
    `subagent_*` events layer on top via `_on_task_*`."""
    if message.parent_tool_use_id is not None:
        return
    content = message.content if isinstance(message.content, list) else []
    tool_results = [b for b in content if isinstance(b, ToolResultBlock)]
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
    """Close the subagent frame. Status maps to `avp.subagent.reason`:
    completed→converged, stopped→interrupted, failed→error (with the summary
    carrying the failure). The notification can arrive many turns after the
    dispatch (async `Agent` tool), or not at all (closed as `abandoned` at
    stop)."""
    if not message.tool_use_id:
        return
    await state.rec.subagent_result(
        message.tool_use_id,
        message.summary or "",
        _TASK_STATUS_TO_REASON.get(message.status, StopReason.converged),
        usage=_task_usage_to_subagent_usage(message.usage),
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
    # TaskProgressMessage, MirrorErrorMessage, StreamEvent, RateLimitEvent:
    # drop. Honest-silent beats fabricated events.

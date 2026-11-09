"""Claude's response boundaries and tool results to Recorder calls."""

import json
import time

from claude_agent_sdk import AssistantMessage, SystemMessage, UserMessage
from claude_agent_sdk.types import StreamEvent, ToolResultBlock
from pydantic import TypeAdapter

from avp.commission import ModelRef
from avp.recorder import Recorder, UsageReport
from avp.reports import ContentBlock, SubagentUsage, ThinkingBlock, ToolUseBlock
from avp.utils.pricing import compute_cost, load_prices

CONTENT = TypeAdapter(ContentBlock)


def error_code(error: str | int | None):
    if error in ("authentication_failed", 401, 403):
        return "auth_error"
    if error in ("billing_error", "rate_limit", 429):
        return "rate_limit"
    return "agent_crash"


def block(raw: dict):
    if raw["type"] == "redacted_thinking":
        return ThinkingBlock(type="thinking", thinking=raw["data"], redacted=True)
    return CONTENT.validate_python(raw)


def tool_content(raw):
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return [
        CONTENT.validate_python(part)
        if part["type"] in ("text", "image")
        else CONTENT.validate_python({"type": "text", "text": json.dumps(part)})
        for part in raw
    ]


def subagent_usage(details):
    """The native Agent result reports aggregate usage for opaque children."""
    native = (details or {}).get("usage")
    if not isinstance(native, dict):
        return None
    values = {
        key: native[key]
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
        if key in native
    }
    if "input_tokens" in values:
        values["input_tokens"] += values.get("cache_read_input_tokens", 0) + values.get(
            "cache_creation_input_tokens", 0
        )
    reasoning = native.get("output_tokens_details", {}).get("thinking_tokens")
    if reasoning is not None:
        values["reasoning_output_tokens"] = reasoning
    usage = SubagentUsage(**values)
    model = details.get("resolvedModel")
    if (
        isinstance(model, str)
        and usage.input_tokens is not None
        and usage.output_tokens is not None
    ):
        usage.cost_usd, usage.cost_source = compute_cost(
            load_prices(),
            ModelRef(provider="anthropic", id=model),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
            cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
        )
    return usage


class Responses:
    def __init__(self, recorder: Recorder, model: str, allowed: set[str]):
        self.rec = recorder
        self.model = model
        self.allowed = allowed
        self.open = {}
        self.subagents = {}
        self.finished_subagents = set()
        self.known_calls = set()
        self.deferred = []
        self.tool_result_metadata = {}
        self.responses = 0
        self.error = None
        self.refused = False

    async def accept(self, message):
        parent = getattr(message, "parent_tool_use_id", None)
        if isinstance(message, SystemMessage) and message.subtype == "task_notification":
            parent = message.data.get("tool_use_id")
        if parent is not None and parent not in self.subagents and self._streaming_call(parent):
            self.deferred.append((parent, message))
            return
        if isinstance(message, AssistantMessage) and message.error:
            self.error = message.error
            await self.rec.error(
                error_code(message.error),
                "\n".join(getattr(b, "text", "") for b in message.content),
            )
        elif isinstance(message, StreamEvent):
            event = message.event
            kind = event["type"]
            parent = message.parent_tool_use_id
            if kind == "message_start":
                if parent in self.open:
                    raise ValueError("Claude started a response before closing its previous one")
                self.open[parent] = {
                    "message": event["message"],
                    "blocks": {},
                    "arguments": {},
                    "started": time.monotonic(),
                }
            elif kind.startswith("content_block_"):
                state = self.open[parent]
                index = event["index"]
                if kind == "content_block_start":
                    state["blocks"][index] = dict(event["content_block"])
                elif kind == "content_block_delta":
                    delta = event["delta"]
                    target = state["blocks"][index]
                    field = {
                        "text_delta": "text",
                        "thinking_delta": "thinking",
                        "signature_delta": "signature",
                    }.get(delta["type"])
                    if field:
                        target[field] = target.get(field, "") + delta[field]
                    elif delta["type"] == "input_json_delta":
                        state["arguments"][index] = (
                            state["arguments"].get(index, "") + delta["partial_json"]
                        )
                    elif delta["type"] == "citations_delta":
                        target.setdefault("citations", []).append(delta["citation"])
                    else:
                        raise ValueError(f"unsupported Claude delta: {delta['type']}")
                elif kind == "content_block_stop" and index in state["arguments"]:
                    state["blocks"][index]["input"] = json.loads(state["arguments"][index])
            elif kind == "message_delta":
                state = self.open[parent]
                state["message"].update(event["delta"])
                state["message"]["usage"].update(event.get("usage", {}))
            elif kind == "message_stop":
                state = self.open.pop(parent)
                native = state["message"]
                blocks = [block(state["blocks"][i]) for i in sorted(state["blocks"])]
                for content in blocks:
                    if isinstance(content, ToolUseBlock) and content.name not in self.allowed:
                        raise ValueError(
                            f"Claude called disabled or undeclared tool {content.name!r}"
                        )
                usage = native["usage"]
                cached = usage.get("cache_read_input_tokens", 0)
                written = usage.get("cache_creation_input_tokens", 0)
                await self.rec.response(
                    blocks,
                    usage=UsageReport(
                        input_tokens=usage["input_tokens"] + cached + written,
                        output_tokens=usage["output_tokens"],
                        cache_read_input_tokens=cached or None,
                        cache_creation_input_tokens=written or None,
                    ),
                    response_model=native["model"] if native["model"] != self.model else None,
                    finish_reasons=[native["stop_reason"]] if native.get("stop_reason") else None,
                    duration_ms=int((time.monotonic() - state["started"]) * 1000),
                    subagent_invocation_id=parent,
                )
                self.known_calls.update(b.id for b in blocks if isinstance(b, ToolUseBlock))
                self.responses += 1
                self.refused |= native.get("stop_reason") == "refusal"
                for content in blocks:
                    if isinstance(content, ToolUseBlock) and content.name in ("Agent", "Task"):
                        self.subagents[content.id] = content.input
                        await self.rec.subagent_invoked(
                            content.id, content.input.get("subagent_type", "general-purpose")
                        )
                await self._flush_deferred()
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for result in message.content:
                if isinstance(result, ToolResultBlock):
                    self.tool_result_metadata[result.tool_use_id] = message.tool_use_result
                    if result.tool_use_id not in self.known_calls and self._streaming_call(
                        result.tool_use_id
                    ):
                        self.deferred.append((result.tool_use_id, result))
                    else:
                        await self._tool_returned(result)
        elif isinstance(message, SystemMessage):
            if message.subtype == "compact_boundary":
                raise ValueError("Claude compaction accounting is not supported")
            if message.subtype == "task_notification":
                data = message.data
                invocation = data.get("tool_use_id")
                if (
                    invocation in self.subagents
                    and self.subagents[invocation].get("run_in_background", False)
                    and invocation not in self.finished_subagents
                ):
                    reason = {
                        "completed": "converged",
                        "failed": "error",
                        "stopped": "interrupted",
                    }[data["status"]]
                    await self.rec.subagent_returned(invocation, data["summary"], reason)
                    self.finished_subagents.add(invocation)

    def _streaming_call(self, invocation):
        return any(
            block.get("type") == "tool_use" and block.get("id") == invocation
            for state in self.open.values()
            for block in state["blocks"].values()
        )

    async def _flush_deferred(self):
        # Claude can execute tools and start children before message_stop. Wait
        # for that boundary so the parent retains one response with full usage.
        waiting, self.deferred = self.deferred, []
        for invocation, message in waiting:
            if invocation not in self.known_calls:
                self.deferred.append((invocation, message))
            elif isinstance(message, ToolResultBlock):
                await self._tool_returned(message)
            else:
                await self.accept(message)

    async def _tool_returned(self, result):
        invocation = result.tool_use_id
        args = self.subagents.get(invocation)
        details = self.tool_result_metadata.pop(invocation, None)
        # Background agents finish with task_notification.
        if (
            args is not None
            and not args.get("run_in_background", False)
            and invocation not in self.finished_subagents
        ):
            await self.rec.subagent_returned(
                invocation,
                str(result.content),
                "error" if result.is_error else "converged",
                usage=subagent_usage(details),
            )
            self.finished_subagents.add(invocation)
        await self.rec.tool_returned(
            invocation,
            tool_content(result.content),
            is_error=result.is_error,
        )

    def finish(self):
        if self.open or self.deferred or not self.responses:
            raise ValueError("Claude ended without complete model responses and usage")

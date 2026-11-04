"""Claude's response boundaries and tool results to Recorder calls."""

import json
import time

from claude_agent_sdk import AssistantMessage, SystemMessage, UserMessage
from claude_agent_sdk.types import StreamEvent, ToolResultBlock
from pydantic import TypeAdapter

from avp.recorder import Recorder, UsageReport
from avp.trajectory import ContentBlock, ThinkingBlock, ToolUseBlock

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


class Responses:
    def __init__(self, recorder: Recorder, model: str, allowed: set[str]):
        self.rec = recorder
        self.model = model
        self.allowed = allowed
        self.open = {}
        self.subagents = {}
        self.finished_subagents = set()
        self.responses = 0
        self.error = None
        self.refused = False

    async def accept(self, message):
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
                self.responses += 1
                self.refused |= native.get("stop_reason") == "refusal"
                for content in blocks:
                    if isinstance(content, ToolUseBlock) and content.name in ("Agent", "Task"):
                        self.subagents[content.id] = content.input
                        await self.rec.subagent_invoked(
                            content.id, content.input.get("subagent_type", "general-purpose")
                        )
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for result in message.content:
                if isinstance(result, ToolResultBlock):
                    invocation = result.tool_use_id
                    args = self.subagents.get(invocation)
                    # Background agents finish with task_notification; keep them open until then.
                    if (
                        args is not None
                        and args.get("run_in_background") is False
                        and invocation not in self.finished_subagents
                    ):
                        await self.rec.subagent_returned(
                            invocation,
                            str(result.content),
                            "error" if result.is_error else "converged",
                        )
                        self.finished_subagents.add(invocation)
                    await self.rec.tool_returned(
                        invocation, tool_content(result.content), is_error=result.is_error
                    )
        elif isinstance(message, SystemMessage):
            if message.subtype == "compact_boundary":
                raise ValueError("Claude compaction accounting is not supported")
            if message.subtype == "task_notification":
                data = message.data
                invocation = data.get("tool_use_id")
                if invocation in self.subagents and invocation not in self.finished_subagents:
                    reason = {
                        "completed": "converged",
                        "failed": "error",
                        "stopped": "interrupted",
                    }[data["status"]]
                    await self.rec.subagent_returned(invocation, data["summary"], reason)
                    self.finished_subagents.add(invocation)

    def finish(self):
        if self.open or not self.responses:
            raise ValueError("Claude ended without complete model responses and usage")

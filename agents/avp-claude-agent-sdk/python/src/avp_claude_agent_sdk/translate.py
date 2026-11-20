"""Claude's streamed responses, tool results, and subagents to Recorder calls.

Claude streams each model response as events; a response is recorded as one
step when it stops. Only translation lives here; step order, result placement,
and cost are the Recorder's job.
"""

import json
from typing import Any

from claude_agent_sdk import AssistantMessage, SystemMessage, UserMessage
from claude_agent_sdk.types import StreamEvent, ToolResultBlock

from avp.recorder import Call, Image, Part, Reasoning, Recorder, ServerResult, Text, Usage
from avp.trajectory import Citation, ErrorCode, StopReason

SUBAGENT_TOOLS = ("Agent", "Task")
"""Claude's tools that start a subagent."""


def error_code(error: str | int | None) -> ErrorCode:
    if error in ("authentication_failed", 401, 403):
        return "auth_error"
    if error in ("billing_error", "rate_limit", 429):
        return "rate_limit"
    return "agent_crash"


def _citation(raw: dict[str, Any]) -> Citation:
    named = {"url": "source_url", "title": "source_title", "document_title": "source_title"}
    return Citation.model_validate({named.get(k, k): v for k, v in raw.items()})


def parts(blocks: list[dict[str, Any]]) -> list[Part]:
    """A response's content blocks as Recorder parts, in order. Server tool
    blocks are server-side calls and their results."""
    result: list[Part] = []
    for block in blocks:
        kind = block["type"]
        if kind == "text":
            citations = [_citation(c) for c in block.get("citations") or []]
            result.append(Text(text=block["text"], citations=citations or None))
        elif kind == "thinking":
            result.append(Reasoning(text=block["thinking"], signature=block.get("signature")))
        elif kind == "redacted_thinking":
            result.append(Reasoning(encrypted_content=block["data"]))
        elif kind in ("tool_use", "server_tool_use"):
            result.append(
                Call(
                    id=block["id"],
                    name=block["name"],
                    arguments=block["input"],
                    server_side=kind == "server_tool_use",
                )
            )
        elif kind.endswith("_tool_result") and "tool_use_id" in block:
            native = block.get("content")
            failed = isinstance(native, dict) and str(native.get("type", "")).endswith("_error")
            result.append(
                ServerResult(
                    call_id=block["tool_use_id"],
                    content=native if isinstance(native, str) else json.dumps(native),
                    is_error=failed,
                    structured_content=None if isinstance(native, str) else native,
                )
            )
        else:
            raise ValueError(f"unsupported Claude content block: {kind}")
    return result


def content(raw: Any, rec: Recorder) -> str | list[Text | Image]:
    """A tool result's content: its text and images. Other parts are kept as JSON text."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    result: list[Text | Image] = []
    for part in raw:
        source = part.get("source") or {}
        if part["type"] == "text":
            result.append(Text(text=part["text"]))
        elif part["type"] == "image" and source.get("type") == "base64":
            result.append(rec.image_base64(source["data"], source["media_type"]))
        else:
            result.append(Text(text=json.dumps(part)))
    return result


def usage(native: dict[str, Any]) -> Usage:
    """Claude's usage. Its `input_tokens` leaves out cached and cache creation
    tokens, which `prompt_tokens` includes."""
    cached = native.get("cache_read_input_tokens") or 0
    written = native.get("cache_creation_input_tokens") or 0
    reasoning = (native.get("output_tokens_details") or {}).get("thinking_tokens")
    return Usage(
        prompt_tokens=native.get("input_tokens", 0) + cached + written,
        completion_tokens=native.get("output_tokens", 0),
        cached_tokens=cached or None,
        cache_creation_input_tokens=written or None,
        reasoning_output_tokens=reasoning,
    )


def subagent_usage(details: Any) -> tuple[Usage, str | None] | None:
    """The total usage Claude reports for a subagent, and the model it ran,
    from the subagent tool's result."""
    native = details.get("usage") if isinstance(details, dict) else None
    if not isinstance(native, dict) or "input_tokens" not in native:
        return None
    model = details.get("resolvedModel")
    return usage(native), model if isinstance(model, str) else None


class Responses:
    """Reports Claude's messages to the Recorder, in order.

    Claude can run a tool, and start its subagent, before the response that
    called it stops. Those messages wait until that response is recorded.
    """

    def __init__(self, rec: Recorder):
        self.rec = rec
        self.open: dict[str | None, dict[str, Any]] = {}
        """Streaming responses, by the subagent call they belong to (None for the root)."""
        self.subagents: dict[str, dict[str, Any]] = {}
        """Each subagent's call arguments, by call id."""
        self.stopped: set[str] = set()
        self.known_calls: set[str] = set()
        self.deferred: list[tuple[str, Any]] = []
        self.result_details: dict[str, Any] = {}
        self.responses = 0
        self.error: str | None = None
        self.refused = False

    async def accept(self, message: Any) -> None:
        parent = getattr(message, "parent_tool_use_id", None)
        if isinstance(message, SystemMessage) and message.subtype == "task_notification":
            parent = message.data.get("tool_use_id")
        if parent is not None and parent not in self.subagents and self._streaming(parent):
            self.deferred.append((parent, message))
            return
        if isinstance(message, AssistantMessage) and message.error:
            self.error = message.error
            await self.rec.error(
                error_code(message.error),
                "\n".join(getattr(b, "text", "") for b in message.content),
            )
        elif isinstance(message, StreamEvent):
            await self._event(message.event, message.parent_tool_use_id)
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for result in message.content:
                if isinstance(result, ToolResultBlock):
                    self.result_details[result.tool_use_id] = message.tool_use_result
                    if result.tool_use_id not in self.known_calls and self._streaming(
                        result.tool_use_id
                    ):
                        self.deferred.append((result.tool_use_id, result))
                    else:
                        await self._result(result)
        elif isinstance(message, SystemMessage):
            if message.subtype == "compact_boundary":
                raise ValueError("Claude compaction accounting is not supported")
            if message.subtype == "task_notification":
                call_id = message.data.get("tool_use_id")
                if (
                    call_id in self.subagents
                    and self.subagents[call_id].get("run_in_background", False)
                    and call_id not in self.stopped
                ):
                    reason: StopReason = {
                        "completed": "converged",
                        "failed": "error",
                        "stopped": "interrupted",
                    }[message.data["status"]]
                    await self._stop_subagent(call_id, reason)

    async def _event(self, event: dict[str, Any], parent: str | None) -> None:
        kind = event["type"]
        if kind == "message_start":
            if parent in self.open:
                raise ValueError("Claude started a response before closing its previous one")
            self.open[parent] = {"message": event["message"], "blocks": {}, "arguments": {}}
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
            native = self.open[parent]["message"]
            native.update(event["delta"])
            native["usage"].update(event.get("usage", {}))
        elif kind == "message_stop":
            await self._step(self.open.pop(parent), parent)

    async def _step(self, state: dict[str, Any], parent: str | None) -> None:
        native = state["message"]
        response = parts([state["blocks"][i] for i in sorted(state["blocks"])])
        calls = [p for p in response if isinstance(p, Call) and not p.server_side]
        stop = native.get("stop_reason")
        await self.rec.step(
            response,
            usage=usage(native["usage"]),
            model_name=native.get("model"),
            finish_reasons=[stop] if stop else None,
            subagent=parent,
        )
        self.known_calls.update(c.id for c in calls)
        self.responses += 1
        self.refused |= stop == "refusal"
        for call in calls:
            if call.name in SUBAGENT_TOOLS:
                self.subagents[call.id] = call.arguments
                await self.rec.subagent_started(
                    call.id,
                    call.arguments.get("subagent_type", "general-purpose"),
                    call.arguments.get("prompt", ""),
                )
        await self._flush()

    def _streaming(self, call_id: str) -> bool:
        """Whether `call_id` is a tool call in a response still streaming."""
        return any(
            block.get("type") == "tool_use" and block.get("id") == call_id
            for state in self.open.values()
            for block in state["blocks"].values()
        )

    async def _flush(self) -> None:
        waiting, self.deferred = self.deferred, []
        for call_id, message in waiting:
            if call_id not in self.known_calls:
                self.deferred.append((call_id, message))
            elif isinstance(message, ToolResultBlock):
                await self._result(message)
            else:
                await self.accept(message)

    async def _stop_subagent(self, call_id: str, reason: StopReason, details: Any = None) -> None:
        reported = subagent_usage(details)
        await self.rec.subagent_stopped(
            call_id,
            reason,
            usage=reported[0] if reported else None,
            model_name=reported[1] if reported else None,
        )
        self.stopped.add(call_id)

    async def _result(self, result: ToolResultBlock) -> None:
        call_id = result.tool_use_id
        details = self.result_details.pop(call_id, None)
        arguments = self.subagents.get(call_id)
        # A background subagent stops with its task notification.
        if (
            arguments is not None
            and not arguments.get("run_in_background", False)
            and call_id not in self.stopped
        ):
            await self._stop_subagent(call_id, "error" if result.is_error else "converged", details)
        await self.rec.result(
            call_id, content(result.content, self.rec), is_error=bool(result.is_error)
        )

    def finish(self) -> None:
        if self.open or self.deferred or not self.responses:
            raise ValueError("Claude ended without complete model responses and usage")

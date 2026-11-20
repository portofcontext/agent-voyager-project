"""Codex's raw response items and tool results to Recorder calls.

Codex reports each model response's items and then its usage; a response is
recorded as one step at that boundary. Only translation lives here; step
order, result placement, and cost are the Recorder's job.
"""

import json
from typing import Any

from openai_codex.models import Notification, UnknownNotification

from avp.recorder import Call, Image, Part, Reasoning, Recorder, Text, Usage
from avp.trajectory import ErrorCode

TOOL_OUTPUTS = {"function_call_output", "custom_tool_call_output", "tool_search_output"}


def notification_params(event: Notification) -> dict:
    if isinstance(event.payload, UnknownNotification):
        if event.method in {"rawResponseItem/completed", "rawResponse/completed"}:
            return event.payload.params
        if event.method in {
            "item/completed",
            "turn/completed",
            "error",
            "model/rerouted",
            "thread/tokenUsage/updated",
            "thread/compacted",
        }:
            raise ValueError(f"Codex SDK could not validate {event.method}")
        return {}
    return event.payload.model_dump(mode="json", by_alias=True, exclude_none=True)


def parts(item: dict[str, Any]) -> list[Part]:
    """A response item as Recorder parts. Messages from other roles have none."""
    kind = item["type"]
    if kind == "message":
        if item["role"] != "assistant":
            return []
        result: list[Part] = []
        for part in item["content"]:
            if part["type"] == "output_text":
                result.append(Text(text=part["text"]))
            elif part["type"] == "refusal":
                result.append(Text(text=part["refusal"], refusal=True))
            else:
                raise ValueError(f"unsupported Codex assistant content: {part['type']}")
        return result
    if kind == "reasoning":
        return [
            Reasoning(
                text="\n".join(part["text"] for part in item.get("summary", [])),
                encrypted_content=item.get("encrypted_content"),
            )
        ]
    if kind in {"function_call", "custom_tool_call", "tool_search_call"}:
        if kind == "function_call":
            arguments = json.loads(item["arguments"])
        elif kind == "custom_tool_call":
            arguments = {"input": item["input"]}
        else:
            if item.get("execution") != "client":
                raise ValueError("Codex server-executed tool search is not supported")
            arguments = item["arguments"]
        if not isinstance(arguments, dict):
            raise ValueError("Codex tool arguments must be an object")
        name = "tool_search" if kind == "tool_search_call" else item["name"]
        if namespace := item.get("namespace"):
            name = f"{namespace}.{name}"
        return [Call(id=item["call_id"], name=name, arguments=arguments)]
    raise ValueError(f"unsupported Codex response item: {kind}")


def usage(native: dict[str, Any]) -> Usage:
    """Codex's usage. As in the Responses API, input tokens include cached
    tokens and output tokens include reasoning tokens."""
    return Usage(
        prompt_tokens=native["inputTokens"],
        completion_tokens=native["outputTokens"],
        cached_tokens=native.get("cachedInputTokens"),
        cache_creation_input_tokens=native.get("cacheWriteInputTokens"),
        reasoning_output_tokens=native.get("reasoningOutputTokens"),
    )


def content(output: Any, rec: Recorder) -> str | list[Text | Image]:
    """A tool result's content: its text and images. Other parts are kept as JSON text."""
    if isinstance(output, str):
        return output
    result: list[Text | Image] = []
    for part in output:
        if part["type"] in {"text", "input_text"}:
            result.append(Text(text=part["text"]))
        elif part["type"] == "image":
            result.append(rec.image_base64(part["data"], part["mimeType"]))
        else:
            result.append(Text(text=json.dumps(part)))
    return result


class Responses:
    """Reports Codex's responses and tool results to the Recorder, in order.

    A tool can return before its response's usage arrives. Those results wait
    until that response is recorded.
    """

    def __init__(self, rec: Recorder) -> None:
        self.rec = rec
        self.model_name: str | None = None
        """The model Codex rerouted to, if it did."""
        self.parts: list[Part] = []
        self.results: list[dict[str, Any]] = []
        self.statuses: dict[str, dict[str, Any]] = {}
        self.calls: set[str] = set()
        self.responses = 0
        self.output = ""
        self.refused = False

    async def accept(self, method: str, params: dict[str, Any]) -> None:
        if method == "model/rerouted":
            self.model_name = params["toModel"]
        elif method == "thread/compacted":
            raise ValueError("Codex context compaction accounting is not supported")
        elif method == "error" and params.get("willRetry") and self.parts:
            raise ValueError("Codex retried a partial response without a usage boundary")
        elif method == "item/completed":
            item = params["item"]
            if item["type"] == "contextCompaction":
                raise ValueError("Codex context compaction accounting is not supported")
            if item["type"] in {"commandExecution", "fileChange", "mcpToolCall"}:
                self.statuses[item["id"]] = item
        elif method == "rawResponseItem/completed":
            item = params["item"]
            if item["type"] in TOOL_OUTPUTS:
                if self.parts:
                    self.results.append(item)
                else:
                    await self._result(item)
                return
            response = parts(item)
            if item["type"] == "message" and item["role"] == "assistant":
                self.output = "".join(p.text for p in response if isinstance(p, Text))
            self.refused |= any(isinstance(p, Text) and p.refusal for p in response)
            self.calls.update(p.id for p in response if isinstance(p, Call))
            self.parts += response
        elif method == "rawResponse/completed":
            await self.rec.step(
                self.parts, usage=usage(params["usage"]), model_name=self.model_name
            )
            self.parts = []
            self.responses += 1
            waiting, self.results = self.results, []
            for item in waiting:
                await self._result(item)

    async def _result(self, item: dict[str, Any]) -> None:
        status = self.statuses.pop(item["call_id"], {})
        failed = status.get("status") in {"failed", "declined"} or status.get(
            "exitCode", 0
        ) not in (None, 0)
        structured = None
        if item["type"] == "tool_search_output":
            if item.get("execution") != "client":
                raise ValueError("Codex server-executed tool search is not supported")
            structured = {"tools": item["tools"]}
            output = json.dumps(structured)
            failed = item.get("status") != "completed"
        elif status.get("type") == "mcpToolCall" and status.get("result") is not None:
            result = status["result"]
            output = result["content"]
            structured = result.get("structuredContent")
            failed = failed or bool(result.get("isError"))
        else:
            output = item["output"]
        await self.rec.result(
            item["call_id"],
            content(output, self.rec),
            is_error=failed,
            structured_content=structured,
        )
        self.calls.discard(item["call_id"])

    def finish(self) -> None:
        if not self.responses or self.parts or self.results or self.calls:
            raise ValueError("Codex ended without complete raw response boundaries and usage")


def error_code(error: dict[str, Any]) -> ErrorCode:
    info = error.get("codexErrorInfo")
    if isinstance(info, dict):
        for detail in info.values():
            if isinstance(detail, dict):
                if detail.get("httpStatusCode") in (401, 403):
                    return "auth_error"
                if detail.get("httpStatusCode") == 429:
                    return "rate_limit"
        return "unknown"
    codes: dict[str, ErrorCode] = {
        "unauthorized": "auth_error",
        "usageLimitExceeded": "rate_limit",
        "rateLimitExceeded": "rate_limit",
        "contextWindowExceeded": "context_limit",
    }
    return codes.get(info, "agent_crash")

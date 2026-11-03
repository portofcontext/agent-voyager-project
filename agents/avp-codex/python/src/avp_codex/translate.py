"""Codex response items to AVP content; the Recorder handles event order and cost."""

import json
import time

from openai_codex.models import Notification, UnknownNotification

from avp.recorder import Recorder, UsageReport
from avp.trajectory import (
    ContentBlock,
    ErrorCode,
    ImageBlock,
    RefusalBlock,
    Source,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)


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


def content(item: dict) -> list[ContentBlock]:
    kind = item["type"]
    if kind == "message":
        if item["role"] != "assistant":
            return []
        blocks = []
        for part in item["content"]:
            if part["type"] == "output_text":
                blocks.append(TextBlock(type="text", text=part["text"], codex=part))
            elif part["type"] == "refusal":
                blocks.append(RefusalBlock(type="refusal", refusal=part["refusal"]))
            else:
                raise ValueError(f"unsupported Codex assistant content: {part['type']}")
        return blocks
    if kind == "reasoning":
        return [
            ThinkingBlock(
                type="thinking",
                thinking="\n".join(part["text"] for part in item.get("summary", [])),
                signature=item.get("encrypted_content"),
                codex=item,
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
        return [ToolUseBlock(type="tool_use", id=item["call_id"], name=name, input=arguments)]
    raise ValueError(f"unsupported Codex response item: {kind}")


def usage(native: dict) -> UsageReport:
    return UsageReport(
        input_tokens=native["inputTokens"],
        output_tokens=native["outputTokens"],
        cache_read_input_tokens=native.get("cachedInputTokens"),
        cache_creation_input_tokens=native.get("cacheWriteInputTokens"),
        reasoning_output_tokens=native.get("reasoningOutputTokens"),
    )


def tool_content(output):
    if isinstance(output, str):
        return output
    result = []
    for part in output:
        if part["type"] in {"text", "input_text"}:
            result.append(TextBlock(type="text", text=part["text"]))
        elif part["type"] == "image":
            result.append(
                ImageBlock(
                    type="image",
                    source=Source(type="base64", media_type=part["mimeType"], data=part["data"]),
                )
            )
        else:
            result.append(TextBlock(type="text", text=json.dumps(part)))
    return result


class Responses:
    """One raw response boundary is one Recorder response, including its tool calls."""

    def __init__(self, recorder: Recorder, model_id: str, disabled: list[str]) -> None:
        self.recorder = recorder
        self.model_id = model_id
        self.response_model = model_id
        self.disabled = set(disabled)
        self.blocks: list[ContentBlock] = []
        self.results: list[dict] = []
        self.statuses: dict[str, dict] = {}
        self.calls: set[str] = set()
        self.completed = 0
        self.output = ""
        self.refused = False
        self.requested = time.monotonic()

    async def accept(self, method: str, params: dict) -> None:
        if method == "model/rerouted":
            self.response_model = params["toModel"]
        elif method == "thread/compacted":
            raise ValueError("Codex context compaction accounting is not supported")
        elif method == "error" and params.get("willRetry") and self.blocks:
            raise ValueError("Codex retried a partial response without a usage boundary")
        elif method == "item/completed":
            item = params["item"]
            if item["type"] == "contextCompaction":
                raise ValueError("Codex context compaction accounting is not supported")
            if item["type"] in {"commandExecution", "fileChange", "mcpToolCall"}:
                self.statuses[item["id"]] = item
        elif method == "rawResponseItem/completed":
            item = params["item"]
            if item["type"] in {
                "function_call_output",
                "custom_tool_call_output",
                "tool_search_output",
            }:
                if self.blocks:
                    self.results.append(item)
                else:
                    await self.result(item)
            else:
                blocks = content(item)
                if item["type"] == "message" and item["role"] == "assistant":
                    self.output = "".join(
                        block.text if isinstance(block, TextBlock) else block.refusal
                        for block in blocks
                        if isinstance(block, (TextBlock, RefusalBlock))
                    )
                for block in blocks:
                    if isinstance(block, ToolUseBlock):
                        if block.name in self.disabled:
                            raise ValueError(f"Codex called the disabled tool {block.name!r}")
                        self.calls.add(block.id)
                    elif isinstance(block, RefusalBlock):
                        self.refused = True
                    self.blocks.append(block)
        elif method == "rawResponse/completed":
            now = time.monotonic()
            await self.recorder.response(
                self.blocks,
                usage=usage(params["usage"]),
                response_model=self.response_model
                if self.response_model != self.model_id
                else None,
                duration_ms=int((now - self.requested) * 1000),
            )
            self.blocks = []
            self.completed += 1
            self.requested = now
            for result in self.results:
                await self.result(result)
            self.results = []

    async def result(self, item: dict) -> None:
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
        await self.recorder.tool_returned(
            item["call_id"], tool_content(output), structured_content=structured, is_error=failed
        )
        self.calls.discard(item["call_id"])
        self.requested = time.monotonic()

    def finish(self) -> None:
        if not self.completed or self.blocks or self.results or self.calls:
            raise ValueError("Codex ended without complete raw response boundaries and usage")


def error_code(error: dict) -> ErrorCode:
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

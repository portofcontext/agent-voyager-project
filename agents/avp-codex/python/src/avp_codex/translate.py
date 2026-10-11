"""Native response items and inference boundaries, without owning Codex's loop."""

from __future__ import annotations

import json

from avp.content import RefusalBlock, TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock
from avp.recorder import Recorder
from avp.trajectory import Usage


def tool_name(item: dict) -> str:
    namespace = item.get("namespace")
    return f"{namespace}.{item['name']}" if namespace else item["name"]


def content(item: dict) -> list:
    kind = item["type"]
    if kind == "message":
        if item["role"] != "assistant":
            return []
        blocks = []
        for part in item["content"]:
            if part["type"] in ("output_text", "input_text"):
                blocks.append(TextBlock(text=part["text"], codex=part))
            elif part["type"] == "refusal":
                blocks.append(RefusalBlock(refusal=part["refusal"]))
            else:
                raise ValueError(f"unsupported Codex assistant content: {part['type']}")
        return blocks
    if kind == "reasoning":
        return [
            ThinkingBlock(
                thinking="\n".join(part["text"] for part in item.get("summary", [])),
                signature=item.get("encrypted_content"),
                codex=item,
            )
        ]
    if kind in ("function_call", "custom_tool_call"):
        args = (
            json.loads(item["arguments"]) if kind == "function_call" else {"input": item["input"]}
        )
        if not isinstance(args, dict):
            raise ValueError("Codex function arguments must be an object")
        return [ToolUseBlock(id=item["call_id"], name=tool_name(item), input=args, codex=item)]
    raise ValueError(f"unsupported Codex response item: {kind}")


def usage(native: dict) -> Usage:
    return Usage(
        input_tokens=native["inputTokens"],
        output_tokens=native["outputTokens"],
        cache_read_input_tokens=native.get("cachedInputTokens"),
        cache_creation_input_tokens=native.get("cacheWriteInputTokens"),
        reasoning_output_tokens=native.get("reasoningOutputTokens"),
    )


class Responses:
    def __init__(self, recorder: Recorder, model: str):
        self.recorder, self.model = recorder, model
        self.response_model = model
        self.pending_calls: set[str] = set()
        self.blocks: list = []
        self.results: list[dict] = []
        self.statuses: dict[str, dict] = {}
        self.completed = 0
        self.output = ""
        self.refused = False

    async def accept(self, method: str, params: dict):
        if method == "model/rerouted":
            self.response_model = "openai/" + params["toModel"]
        elif method == "item/completed":
            item = params["item"]
            if item["type"] in ("mcpToolCall", "commandExecution", "fileChange"):
                self.statuses[item["id"]] = item
        elif method == "rawResponseItem/completed":
            item = params["item"]
            if item["type"] in ("function_call_output", "custom_tool_call_output"):
                if self.blocks:
                    self.results.append(item)
                else:
                    await self.result(item)
            else:
                blocks = content(item)
                self.blocks.extend(blocks)
                for block in blocks:
                    if isinstance(block, ToolUseBlock):
                        self.pending_calls.add(block.id)
                    if isinstance(block, TextBlock):
                        self.output = block.text
                    if isinstance(block, RefusalBlock):
                        self.refused = True
        elif method == "rawResponse/completed":
            await self.recorder.assistant(
                self.blocks,
                usage(params["usage"]),
                model=self.response_model,
                request_model=self.model,
            )
            self.blocks = []
            self.completed += 1
            for item in self.results:
                await self.result(item)
            self.results = []

    async def result(self, item: dict):
        status = self.statuses.pop(item["call_id"], {})
        failed = status.get("status") in ("failed", "declined") or status.get(
            "exitCode", 0
        ) not in (None, 0)
        structured = None
        if status.get("type") == "mcpToolCall" and status.get("result") is not None:
            result = status["result"]
            output = result["content"]
            failed = failed or bool(result.get("isError"))
            structured = result.get("structuredContent")
        else:
            output = item["output"]
        if isinstance(output, list):
            # Native function outputs use input_text; MCP outputs use text.
            # Preserve non-text payloads as JSON rather than silently discarding.
            output = [
                TextBlock(text=part["text"])
                if part.get("type") in ("input_text", "text")
                else TextBlock(text=json.dumps(part))
                for part in output
            ]
        await self.recorder.tool_result(
            item["call_id"],
            ToolResultBlock(
                tool_use_id=item["call_id"],
                content=output,
                is_error=failed,
                structured_content=structured,
                codex=item,
            ),
        )
        self.pending_calls.discard(item["call_id"])

    def finish(self):
        if not self.completed or self.blocks or self.results or self.pending_calls:
            raise ValueError("Codex ended without complete raw response boundaries and usage")


def error_code(error: dict):
    """Classify structured native provider failures without matching model text."""
    from avp.trajectory import ErrorCode

    info = error.get("codexErrorInfo")
    if isinstance(info, dict):
        for detail in info.values():
            if isinstance(detail, dict):
                status = detail.get("httpStatusCode")
                if status in (401, 403):
                    return ErrorCode.auth_error
                if status == 429:
                    return ErrorCode.rate_limit
        return ErrorCode.network_error
    return {
        "unauthorized": ErrorCode.auth_error,
        "usageLimitExceeded": ErrorCode.rate_limit,
        "rateLimitExceeded": ErrorCode.rate_limit,
        "contextWindowExceeded": ErrorCode.context_limit,
    }.get(info, ErrorCode.agent_crash)

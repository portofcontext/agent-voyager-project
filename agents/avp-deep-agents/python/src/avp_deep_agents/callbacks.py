"""Observe native graph callbacks; the Recorder owns event order and accounting."""

import asyncio
import time

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import ToolMessage
from langchain_core.outputs import ChatGeneration

from avp.reports import ToolUseBlock
from avp_deep_agents import translate


class RecorderCallbacks(AsyncCallbackHandler):
    raise_error = True
    run_inline = True

    def __init__(self, recorder, model, subagent_names):
        self.rec = recorder
        self.model = model
        self.subagent_names = subagent_names
        self.parents = {}
        self.started = {}
        self.calls = {}
        self.frames = {}
        self.pending = {}
        self.returned = set()
        self.refused = set()
        self.lock = asyncio.Lock()

    def frame(self, run_id):
        while run_id is not None:
            if run_id in self.frames:
                return self.frames[run_id]
            run_id = self.parents.get(run_id)
        return None

    async def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self.parents[run_id] = parent_run_id

    async def on_chain_end(self, outputs, *, run_id, parent_run_id=None, **kwargs):
        if parent_run_id is None and isinstance(outputs, dict):
            await self.settle(outputs.get("messages", []))
        self.parents.pop(run_id, None)

    async def on_chain_error(self, error, *, run_id, **kwargs):
        self.parents.pop(run_id, None)

    async def on_chat_model_start(
        self, serialized, messages, *, run_id, parent_run_id=None, **kwargs
    ):
        if (kwargs.get("metadata") or {}).get("lc_source") == "summarization":
            raise ValueError("Deep Agents context compaction cannot be recorded by this adapter")
        self.parents[run_id] = parent_run_id
        self.started[run_id] = time.monotonic()
        if messages:
            await self.settle(messages[0])

    async def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        generation = response.generations[0][0]
        if not isinstance(generation, ChatGeneration):
            raise ValueError("Deep Agents did not return a chat-model response")
        message = generation.message
        blocks = translate.content(message)
        scope = self.frame(parent_run_id)
        if any(b.type == "refusal" for b in blocks):
            self.refused.add(scope)
        metadata = message.response_metadata
        actual = metadata.get("model_name") or metadata.get("model")
        finish = (
            metadata.get("finish_reason") or metadata.get("stop_reason") or metadata.get("status")
        )
        async with self.lock:
            await self.rec.response(
                blocks,
                usage=translate.usage(message.usage_metadata),
                response_model=actual if actual and actual != self.model.id else None,
                finish_reasons=[finish] if finish else None,
                duration_ms=int((time.monotonic() - self.started.pop(run_id)) * 1000),
                subagent_invocation_id=scope,
            )
            self.pending.update({b.id: b.input for b in blocks if isinstance(b, ToolUseBlock)})
        self.parents.pop(run_id, None)

    async def on_llm_error(self, error, *, run_id, **kwargs):
        self.started.pop(run_id, None)
        self.parents.pop(run_id, None)

    async def on_tool_start(
        self,
        serialized,
        input_str,
        *,
        run_id,
        parent_run_id=None,
        tool_call_id=None,
        inputs=None,
        **kwargs,
    ):
        self.parents[run_id] = parent_run_id
        if tool_call_id not in self.pending:
            return
        self.calls[run_id] = tool_call_id
        args = inputs or self.pending[tool_call_id]
        if serialized["name"] == "task" and args.get("subagent_type") in self.subagent_names:
            async with self.lock:
                await self.rec.subagent_invoked(
                    tool_call_id,
                    args["subagent_type"],
                    subagent_invocation_id=self.frame(parent_run_id),
                )
            self.frames[run_id] = tool_call_id

    async def finish_tool(self, run_id, content, is_error=False, structured=None):
        call_id = self.calls.pop(run_id, None)
        if call_id is None:
            return
        async with self.lock:
            if run_id in self.frames:
                reason = (
                    "error" if is_error else "refused" if call_id in self.refused else "converged"
                )
                await self.rec.subagent_returned(call_id, str(content), reason)
                self.frames.pop(run_id)
            await self.rec.tool_returned(
                call_id,
                translate.tool_content(content),
                is_error=is_error,
                structured_content=structured,
            )
            self.returned.add(call_id)
            self.pending.pop(call_id, None)
        self.parents.pop(run_id, None)

    async def on_tool_end(self, output, *, run_id, **kwargs):
        call_id = self.calls.get(run_id)
        message = output if isinstance(output, ToolMessage) else None
        update = getattr(output, "update", None)
        if isinstance(update, dict):
            message = next(
                (
                    m
                    for m in update.get("messages", [])
                    if isinstance(m, ToolMessage) and m.tool_call_id == call_id
                ),
                None,
            )
        if message is not None:
            artifact = message.artifact
            structured = artifact.get("structured_content") if isinstance(artifact, dict) else None
            await self.finish_tool(run_id, message.content, message.status == "error", structured)
        else:
            await self.finish_tool(run_id, str(output))

    async def on_tool_error(self, error, *, run_id, **kwargs):
        await self.finish_tool(run_id, str(error) or type(error).__name__, True)

    async def settle(self, messages):
        for message in messages:
            if (
                isinstance(message, ToolMessage)
                and message.tool_call_id in self.pending
                and message.tool_call_id not in self.returned
            ):
                async with self.lock:
                    await self.rec.tool_returned(
                        message.tool_call_id,
                        translate.tool_content(message.content),
                        is_error=message.status == "error",
                    )
                    self.returned.add(message.tool_call_id)
                    self.pending.pop(message.tool_call_id, None)

    def finish(self):
        if self.started or self.pending or self.frames:
            raise ValueError("Deep Agents ended with incomplete responses, tools, or subagents")

"""`AvpCallbackHandler`: record any LangChain / LangGraph run as an AVP trajectory.

Attach it to a run's callbacks and it reports what the run did to a
`Recorder`; the caller owns the rest of the trajectory (`prelude`, `start`,
`stop`). It works on any graph that calls LangChain chat models and tools,
not only Deep Agents:

    rec = Recorder(sink, provider="openai", prices=load_default_prices())
    await rec.prelude(commission, descriptor)
    await rec.start(request_model="openai/gpt-5-mini", tools=[...])
    handler = AvpCallbackHandler(rec, request_model="openai/gpt-5-mini")
    result = await graph.ainvoke(inputs, {"callbacks": [handler]})
    await rec.stop(StopReason.converged, result["messages"][-1].text)

- Each chat-model call that ends (`on_llm_end`) is one `assistant` turn with
  that call's own `usage_metadata`, response model, finish reasons, and
  duration; its tool calls are `tool_use` blocks. A call that fails
  (`on_llm_error`, e.g. an attempt a retry wrapper repeats) reports nothing.
- A tool run is keyed by its `tool_call_id`; its end (or error) is the
  `tool_result`. Parallel calls pair by id in whatever order they finish.
  Results produced without a tool run (a middleware that rejects a call, a
  tool name the model invented) are picked up from the `ToolMessage`s the next
  model call or the root run's output carries.
- A call to `subagent_tool` (Deep Agents' `task`) opens a subagent frame. LangChain
  propagates callbacks into the child graph, so every run under that tool run
  is the child's: its inferences roll up onto `subagent_result(usage=...)`
  and its tool calls stay out of the parent's trajectory.

Recording errors are adapter bugs, so `raise_error` is on: they propagate into
the run rather than being logged and dropped.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage

from avp.pricing import COST_SOURCE_UNKNOWN, PriceTable, compute_cost, load_default_prices
from avp.recorder import Recorder
from avp.trajectory import StopReason, SubagentUsage, Usage
from avp_deep_agents import translate


@dataclasses.dataclass
class _Frame:
    """A subagent frame: the parent's tool call and its child's spend so far."""

    call_id: str
    turns: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float | None = 0.0

    def usage(self) -> SubagentUsage:
        return SubagentUsage(
            turns=self.turns,
            tokens_input=self.tokens_input,
            tokens_output=self.tokens_output,
            cost_usd=self.cost_usd,
        )


class AvpCallbackHandler(AsyncCallbackHandler):
    """Reports a LangChain run's model calls and tool calls to a `Recorder`.

    Args:
        recorder: The run's Recorder, already `start`ed.
        request_model: `avp.request.model` for every turn (an `origin/model`
            slug). Defaults to the model LangChain reports for each call.
        prices: Price table for the subagent spend rollup (parent turns are
            priced by the Recorder). Defaults to the bundled table.
        subagent_tool: The tool whose calls run a child agent.
    """

    raise_error = True

    def __init__(
        self,
        recorder: Recorder,
        *,
        request_model: str | None = None,
        prices: PriceTable | None = None,
        subagent_tool: str = "task",
    ) -> None:
        self.recorder = recorder
        self.request_model = request_model
        self._prices = prices if prices is not None else load_default_prices()
        self._subagent_tool = subagent_tool
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()
        self._parents: dict[UUID, UUID | None] = {}
        self._started: dict[UUID, tuple[float, str | None]] = {}
        self._calls: dict[UUID, str] = {}
        self._frames: dict[UUID, _Frame] = {}
        self._open: set[str] = set()

    async def _owned(self, work: Coroutine[Any, Any, None]) -> None:
        """Run `work` on the loop that runs the graph. LangChain delivers the
        callbacks of a sync tool from its worker thread, on a fresh loop; the
        Recorder and its sink belong to the run's loop."""
        loop = asyncio.get_running_loop()
        if self._loop is None or self._loop.is_closed():
            self._loop = loop
        if loop is self._loop:
            await work
        else:
            await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(work, self._loop))

    # ── run tree ──────────────────────────────────────────────────────────

    def _frame_of(self, run_id: UUID | None) -> _Frame | None:
        """The subagent frame `run_id` runs inside, if any."""
        while run_id is not None:
            if (frame := self._frames.get(run_id)) is not None:
                return frame
            run_id = self._parents.get(run_id)
        return None

    async def _track(self, run_id: UUID, parent_run_id: UUID | None) -> None:
        self._parents[run_id] = parent_run_id

    async def _forget(self, run_id: UUID) -> None:
        self._parents.pop(run_id, None)
        self._started.pop(run_id, None)

    async def on_chain_start(
        self,
        serialized: Any,
        inputs: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **_: Any,
    ) -> None:
        await self._owned(self._track(run_id, parent_run_id))

    async def on_chain_end(
        self, outputs: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **_: Any
    ) -> None:
        await self._owned(self._forget(run_id))
        if parent_run_id is None and isinstance(outputs, dict):
            await self._owned(self._settle(outputs.get("messages") or []))

    async def on_chain_error(self, error: BaseException, *, run_id: UUID, **_: Any) -> None:
        await self._owned(self._forget(run_id))

    async def on_retriever_start(
        self,
        serialized: Any,
        query: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **_: Any,
    ) -> None:
        await self._owned(self._track(run_id, parent_run_id))

    # ── model calls ───────────────────────────────────────────────────────

    async def on_chat_model_start(
        self,
        serialized: Any,
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        listed_model = (metadata or {}).get("ls_model_name")
        await self._owned(self._model_start(run_id, parent_run_id, listed_model, messages))

    async def on_llm_start(
        self,
        serialized: Any,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **_: Any,
    ) -> None:
        await self._owned(self._model_start(run_id, parent_run_id, None, []))

    async def on_llm_end(
        self, response: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **_: Any
    ) -> None:
        await self._owned(self._model_end(response, run_id, parent_run_id))

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **_: Any) -> None:
        await self._owned(self._forget(run_id))

    async def _model_start(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        listed_model: str | None,
        messages: list[list[BaseMessage]],
    ) -> None:
        self._parents[run_id] = parent_run_id
        self._started[run_id] = (time.monotonic(), listed_model)
        if self._frame_of(parent_run_id) is None and messages:
            await self._settle(messages[0])

    async def _model_end(self, response: Any, run_id: UUID, parent_run_id: UUID | None) -> None:
        started, listed_model = self._started.get(run_id, (time.monotonic(), None))
        await self._forget(run_id)
        generation = response.generations[0][0] if response.generations else None
        message = getattr(generation, "message", None)
        if message is None:
            return
        usage = translate.usage(message.usage_metadata)
        model = translate.response_model(message)
        request_model = self.request_model or listed_model
        if (frame := self._frame_of(parent_run_id)) is not None:
            self._roll_up(frame, usage, model, request_model)
            return
        blocks = translate.content(message)
        async with self._lock:
            await self.recorder.assistant(
                blocks,
                usage,
                model=model,
                request_model=request_model,
                finish_reasons=translate.finish_reasons(message),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            self._open.update(b.id for b in blocks if b.type == "tool_use")

    def _roll_up(
        self, frame: _Frame, usage: Usage | None, model: str | None, request_model: str | None
    ) -> None:
        frame.turns += 1
        if usage is None:
            frame.cost_usd = None
            return
        frame.tokens_input += usage.input_tokens
        frame.tokens_output += usage.output_tokens
        if frame.cost_usd is None:
            return
        for candidate in dict.fromkeys(m for m in (model, request_model) if m):
            cost, source = compute_cost(
                candidate,
                provider=self.recorder.provider,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read=usage.cache_read_input_tokens or 0,
                cache_write=usage.cache_creation_input_tokens or 0,
                prices=self._prices,
            )
            if source != COST_SOURCE_UNKNOWN:
                frame.cost_usd += cost
                return
        frame.cost_usd = None

    # ── tool calls ────────────────────────────────────────────────────────

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        inputs: dict[str, Any] | None = None,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name", kwargs.get("name"))
        await self._owned(self._tool_start(run_id, parent_run_id, name, inputs, tool_call_id))

    async def on_tool_end(self, output: Any, *, run_id: UUID, **_: Any) -> None:
        await self._owned(self._tool_end(output, run_id))

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **_: Any) -> None:
        await self._owned(self._tool_error(error, run_id))

    async def _tool_start(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        name: str | None,
        inputs: dict[str, Any] | None,
        call_id: str | None,
    ) -> None:
        self._parents[run_id] = parent_run_id
        if call_id not in self._open or self._frame_of(parent_run_id) is not None:
            return
        self._calls[run_id] = call_id
        if name == self._subagent_tool:
            async with self._lock:
                await self.recorder.subagent_start(
                    call_id, (inputs or {}).get("subagent_type") or name
                )
            self._frames[run_id] = _Frame(call_id)

    async def _tool_end(self, output: Any, run_id: UUID) -> None:
        await self._forget(run_id)
        if (call_id := self._calls.pop(run_id, None)) is None:
            return
        result, is_error, structured = translate.tool_result(output, call_id)
        # A child that ran hands back a `Command`; a plain result is the tool
        # refusing the call (Deep Agents' answer to an unknown subagent type).
        refused = run_id in self._frames and getattr(output, "update", None) is None
        await self._finish(run_id, call_id, result, is_error or refused, structured)

    async def _tool_error(self, error: BaseException, run_id: UUID) -> None:
        await self._forget(run_id)
        if (call_id := self._calls.pop(run_id, None)) is None:
            return
        await self._finish(run_id, call_id, str(error) or type(error).__name__, True, None)

    async def _finish(
        self,
        run_id: UUID,
        call_id: str,
        result: str | list[Any],
        failed: bool,
        structured: dict[str, Any] | None,
    ) -> None:
        frame = self._frames.pop(run_id, None)
        async with self._lock:
            if frame is not None:
                await self.recorder.subagent_result(
                    call_id,
                    translate.result_text(result),
                    StopReason.error if failed else StopReason.converged,
                    usage=frame.usage(),
                )
            self._open.discard(call_id)
            await self.recorder.tool_result(
                call_id, result, is_error=failed, structured_content=structured
            )

    async def _settle(self, messages: list[Any]) -> None:
        """Report results for open calls that never ran as a tool (rejected
        by middleware, or naming a tool that doesn't exist), from the
        `ToolMessage`s in the conversation."""
        running = set(self._calls.values())
        for message in messages:
            call_id = getattr(message, "tool_call_id", None)
            if call_id in self._open and call_id not in running:
                result, is_error, structured = translate.tool_result(message, call_id)
                async with self._lock:
                    self._open.discard(call_id)
                    await self.recorder.tool_result(
                        call_id, result, is_error=is_error, structured_content=structured
                    )

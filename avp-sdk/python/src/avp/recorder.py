"""Write an agent's Trajectory to the Trajectory spec's rules for agents.

The agent reports what its runtime did; the Recorder decides which events to
write and in what order. Using it is optional: an agent can write its events by
hand.

    rec = Recorder(sink)
    commission = await rec.begin(received, descriptor)  # None when refused
    await rec.start(AgentStarted(prompt=..., model=...))
    await rec.response(content, usage=UsageReport(input_tokens=..., output_tokens=...))
    await rec.tool_returned("toolu_01", "the result")
    await rec.stop("converged", output="...")

While a response is open, the events it led to wait and are written after its
`assistant_message`. A response reported with no `key` closes at once. Chunks
of one streamed response share a `key`: they merge until a different key, a
response with no key, `close_response`, or a result for one of its tool calls.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from avp._base import AVP_VERSION, EventSink
from avp.commission import Commission, ModelRef
from avp.descriptor import AgentDescriptor
from avp.trajectory import (
    AgentDescribed,
    AgentDescribedEvent,
    AgentStarted,
    AgentStartedEvent,
    AgentStopped,
    AgentStoppedEvent,
    AssistantMessage,
    AssistantMessageEvent,
    ContentBlock,
    ErrorCode,
    ErrorOccurred,
    ErrorOccurredEvent,
    Event,
    ImageBlock,
    RunRequested,
    RunRequestedEvent,
    StopReason,
    SubagentInvoked,
    SubagentInvokedEvent,
    SubagentReturned,
    SubagentReturnedEvent,
    SubagentUsage,
    TextBlock,
    ToolInvoked,
    ToolInvokedEvent,
    ToolResultBlock,
    ToolReturned,
    ToolReturnedEvent,
    ToolUseBlock,
    Usage,
)
from avp.utils.preflight import check_commission
from avp.utils.pricing import Prices, compute_cost, load_prices

ABANDONED_TEXT = "The run ended while the subagent was still running."
UNRETURNED_TEXT = "The run ended before the tool returned."
STOPPED_BEFORE_START_TEXT = "The run stopped before agent_started."


class RecorderError(Exception):
    """A report the Recorder can't place: an unknown or repeated ID, or a report
    the run's state doesn't allow. The Recorder writes nothing for it and keeps
    its state."""


class UsageReport(BaseModel):
    """A response's token counts as the runtime reports them, for one response
    only. The Recorder adds `cost_usd` and `cost_source`."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    """The cost the service or runtime reported, if any."""

    @model_validator(mode="after")
    def _cache_within_input(self) -> Self:
        cached = (self.cache_read_input_tokens or 0) + (self.cache_creation_input_tokens or 0)
        if cached > self.input_tokens:
            raise ValueError("cache read and creation tokens exceed input_tokens")
        return self


@dataclass
class _Call:
    name: str
    input: dict[str, JsonValue]
    mcp_server_id: str | None
    subagent_invocation_id: str | None
    time: datetime
    returned: bool = False


@dataclass
class _Subagent:
    name: str
    parent: str | None
    time: datetime
    reason: StopReason | None = None
    """Set when it returns."""


@dataclass
class _Response:
    key: str | None
    model: ModelRef
    subagent_invocation_id: str | None
    opened: datetime
    last: datetime
    content: list[ContentBlock] = field(default_factory=list)
    usage: UsageReport | None = None
    response_model: str | None = None
    finish_reasons: list[str] | None = None
    duration_ms: int | None = None
    meta: dict[str, JsonValue] = field(default_factory=dict)
    call_ids: set[str] = field(default_factory=set)
    waiting: list[Event] = field(default_factory=list)
    """The events it led to, written after its `assistant_message`."""
    tool_returned: bool = False


def _has_content(content: list[ContentBlock]) -> bool:
    return any(not (isinstance(block, TextBlock) and not block.text) for block in content)


def _ms(start: datetime, end: datetime) -> int:
    return max(0, round((end - start).total_seconds() * 1000))


def _refusal(error: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'Commission'}: {e['msg']}" for e in error.errors()
    )
    return f"the Commission doesn't match the spec: {problems}"


class Recorder:
    """Writes one run's Trajectory to `sink`.

    `prices` defaults to `load_prices()`, loaded on the first response to price.
    `run_id` is for an agent that writes `run_requested` and `agent_described`
    itself; `begin` sets it otherwise. `now` and `new_id` make tests repeatable.
    """

    def __init__(
        self,
        sink: EventSink,
        *,
        run_id: str | None = None,
        prices: Prices | None = None,
        now: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._sink = sink
        self._prices = prices
        self._now = now or (lambda: datetime.now(UTC))
        self._new_id = new_id or (lambda: str(uuid.uuid4()))
        self.run_id = run_id or self._new_id()
        self._begun = False
        self._started: AgentStarted | None = None
        self.ended = False
        """The Trajectory has its last event."""
        self._response: _Response | None = None
        self._calls: dict[str, _Call] = {}
        self._subagents: dict[str, _Subagent] = {}
        self._reported_responses: set[str] = set()
        """Subagents with responses of their own as events."""

    # Writing

    def _event(self, event_type: type[Any], name: str, data: BaseModel, **extra: Any) -> Any:
        return event_type(
            avp_version=AVP_VERSION,
            id=self._new_id(),
            time=extra.pop("time", None) or self._now(),
            run_id=self.run_id,
            type=name,
            data=data,
            **extra,
        )

    async def _write(self, event: Event) -> None:
        """Write now, or after the open response's `assistant_message`."""
        if self._response is not None:
            self._response.waiting.append(event)
        else:
            await self._sink(event)

    def _check(self, report: str, *, started: bool = True) -> None:
        if self.ended:
            raise RecorderError(f"{report}: the run has ended")
        if started and self._started is None:
            raise RecorderError(f"{report}: called before start")

    # The run

    async def begin(self, received: JsonValue, descriptor: AgentDescriptor) -> Commission | None:
        """Write `run_requested` with the Commission exactly as received (`None`
        when the run has none) and `agent_described`, then check the Commission.

        Returns the Commission to run, or None. When the Commission doesn't match
        the spec or fails `check_commission`, writes `error_occurred`
        (`invalid_commission`), which ends the run (`ended` is then true).
        """
        self._check("begin", started=False)
        if self._begun or self._started is not None:
            raise RecorderError("begin: called twice, or after start")
        self._begun = True
        commission, refusal = None, None
        if received is not None:
            try:
                commission = Commission.model_validate(received)
            except ValidationError as error:
                refusal = _refusal(error)
            run_id = commission.run_id if commission else None
            if run_id is None and isinstance(received, dict):
                run_id = received.get("run_id")
            if isinstance(run_id, str):
                self.run_id = run_id
        await self._sink(
            self._event(RunRequestedEvent, "run_requested", RunRequested(commission=received))
        )
        await self._sink(
            self._event(
                AgentDescribedEvent, "agent_described", AgentDescribed(descriptor=descriptor)
            )
        )
        if commission is not None:
            refusal = check_commission(commission, descriptor)
        if refusal is not None:
            await self.error("invalid_commission", refusal)
            return None
        return commission

    async def start(
        self, started: AgentStarted, *, meta: dict[str, JsonValue] | None = None
    ) -> None:
        """Write `agent_started`. Its `tools` give each `tool_invoked` its
        `mcp_server_id`, and its `model` is each response's default."""
        self._check("start", started=False)
        if self._started is not None:
            raise RecorderError("start: called twice")
        self._started = started
        await self._sink(self._event(AgentStartedEvent, "agent_started", started, meta=meta))

    async def error(
        self, code: ErrorCode, message: str, *, subagent_invocation_id: str | None = None
    ) -> None:
        """Write `error_occurred`. Before `start` it ends the run; after, it
        doesn't, and `stop("error")` should follow when the run failed."""
        self._check("error", started=False)
        data = ErrorOccurred(
            error_code=code, error_message=message, subagent_invocation_id=subagent_invocation_id
        )
        if self._started is None:
            self.ended = True
            await self._sink(self._event(ErrorOccurredEvent, "error_occurred", data))
            return
        await self._write(self._event(ErrorOccurredEvent, "error_occurred", data))

    async def stop(self, reason: StopReason, output: JsonValue = None) -> None:
        """End the run: close the open response, return every subagent still
        running as `abandoned` and every tool call still running as an error,
        and write `agent_stopped`. A `converged` stop with an abandoned subagent
        becomes `abandoned`.

        Before `start`, writes `error_occurred` (`agent_crash`) instead, as the
        spec asks of a run stopped from outside. Does nothing once the run has
        ended, so it is safe in cleanup code.
        """
        if self.ended:
            return
        if self._started is None:
            await self.error("agent_crash", STOPPED_BEFORE_START_TEXT)
            return
        await self.close_response()
        running = [id for id, subagent in self._subagents.items() if subagent.reason is None]
        for invocation_id in running:
            await self.subagent_returned(invocation_id, ABANDONED_TEXT, "abandoned")
        for call_id in [id for id, call in self._calls.items() if not call.returned]:
            await self.tool_returned(call_id, UNRETURNED_TEXT, is_error=True)
        if running and reason == "converged":
            reason = "abandoned"
        self.ended = True
        stopped = AgentStopped(reason=reason, output=output)
        await self._sink(self._event(AgentStoppedEvent, "agent_stopped", stopped))

    # Responses

    async def response(
        self,
        content: list[ContentBlock],
        *,
        usage: UsageReport | None = None,
        model: ModelRef | None = None,
        response_model: str | None = None,
        finish_reasons: list[str] | None = None,
        duration_ms: int | None = None,
        subagent_invocation_id: str | None = None,
        key: str | None = None,
        meta: dict[str, JsonValue] | None = None,
    ) -> None:
        """Report a model response, or one chunk of a streamed response.

        `model` defaults to `agent_started`'s. Chunks with the same `key` merge:
        content appends, `response_model` keeps its first value, and the other
        fields keep their last. `duration_ms` defaults to the time from the first
        chunk to the last. A `tool_invoked` is written for each `tool_use` block;
        `server_tool_use` blocks get none, as the spec says.
        """
        self._check("response")
        assert self._started is not None
        calls = [block for block in content if isinstance(block, ToolUseBlock)]
        ids = [call.id for call in calls]
        repeated = next((id for id in ids if id in self._calls or ids.count(id) > 1), None)
        if repeated is not None:
            raise RecorderError(f"response: tool_use id {repeated!r} was already used")
        open_ = self._response
        if open_ is not None and (
            key is None
            or key != open_.key
            or open_.tool_returned
            or subagent_invocation_id != open_.subagent_invocation_id
        ):
            await self.close_response()
        now = self._now()
        if self._response is None:
            self._response = _Response(
                key=key,
                model=model or self._started.model,
                subagent_invocation_id=subagent_invocation_id,
                opened=now,
                last=now,
            )
        response = self._response
        response.last = now
        response.content.extend(content)
        if usage is not None:
            response.usage = usage
        if response.response_model is None:
            response.response_model = response_model
        if finish_reasons is not None:
            response.finish_reasons = finish_reasons
        if duration_ms is not None:
            response.duration_ms = duration_ms
        if meta:
            response.meta.update(meta)
        if subagent_invocation_id is not None:
            self._reported_responses.add(subagent_invocation_id)
        mcp_servers = {tool.name: tool.mcp_server_id for tool in self._started.tools or []}
        for call in calls:
            self._calls[call.id] = _Call(
                name=call.name,
                input=call.input,
                mcp_server_id=mcp_servers.get(call.name),
                subagent_invocation_id=subagent_invocation_id,
                time=now,
            )
            response.call_ids.add(call.id)
            invoked = ToolInvoked(
                tool_call_id=call.id,
                tool_name=call.name,
                tool_input=call.input,
                mcp_server_id=mcp_servers.get(call.name),
                subagent_invocation_id=subagent_invocation_id,
            )
            response.waiting.append(self._event(ToolInvokedEvent, "tool_invoked", invoked))
        if key is None:
            await self.close_response()

    async def usage(self, usage: UsageReport, *, key: str | None = None) -> None:
        """Set the open response's usage, for a runtime that reports token counts
        after the content. With `key`, it must be the open response's."""
        self._check("usage")
        response = self._response
        if response is None or (key is not None and key != response.key):
            raise RecorderError(f"usage: no open response with key {key!r}")
        response.usage = usage

    async def close_response(self) -> None:
        """Write the open response's `assistant_message`, then the events it led
        to. A response with no content gets no `assistant_message`, as the spec
        asks. Does nothing when no response is open."""
        response = self._response
        if response is None:
            return
        self._response = None
        if _has_content(response.content):
            await self._sink(self._assistant_message(response))
        for event in response.waiting:
            await self._sink(event)

    def _assistant_message(self, response: _Response) -> Event:
        reported = response.usage
        if reported is None:
            usage = Usage(input_tokens=0, output_tokens=0, cost_usd=0, cost_source="unknown")
        else:
            if self._prices is None and reported.cost_usd is None:
                self._prices = load_prices()
            cost_usd, cost_source = compute_cost(
                self._prices or Prices(fetched=self._now(), models={}),
                response.model,
                input_tokens=reported.input_tokens,
                output_tokens=reported.output_tokens,
                cache_read_input_tokens=reported.cache_read_input_tokens or 0,
                cache_creation_input_tokens=reported.cache_creation_input_tokens or 0,
                response_model=response.response_model,
                reported_cost_usd=reported.cost_usd,
            )
            usage = Usage(
                **reported.model_dump(exclude={"cost_usd"}),
                cost_usd=cost_usd,
                cost_source=cost_source,
            )
        message = AssistantMessage(
            content=response.content,
            model=response.model,
            response_model=response.response_model,
            finish_reasons=response.finish_reasons,
            duration_ms=(
                response.duration_ms
                if response.duration_ms is not None
                else _ms(response.opened, response.last)
            ),
            usage=usage,
            subagent_invocation_id=response.subagent_invocation_id,
        )
        return self._event(
            AssistantMessageEvent,
            "assistant_message",
            message,
            time=response.last,
            meta=response.meta or None,
        )

    # Tools

    async def tool_returned(
        self,
        call_id: str,
        content: str | list[TextBlock | ImageBlock],
        *,
        is_error: bool | None = None,
        structured_content: dict[str, JsonValue] | None = None,
    ) -> None:
        """Write the `tool_returned` for a `tool_use` block. When the call
        started a subagent that has returned, `is_error` is set from the
        subagent's reason, as the spec asks."""
        self._check("tool_returned")
        call = self._calls.get(call_id)
        if call is None or call.returned:
            state = "unknown" if call is None else "already returned"
            raise RecorderError(f"tool_returned: tool call {call_id!r} is {state}")
        call.returned = True
        subagent = self._subagents.get(call_id)
        if subagent is not None and subagent.reason is not None:
            is_error = subagent.reason != "converged"
        if self._response is not None and call_id in self._response.call_ids:
            self._response.tool_returned = True
        returned = ToolReturned(
            tool_call_id=call_id,
            tool_name=call.name,
            duration_ms=_ms(call.time, self._now()),
            tool_result=ToolResultBlock(
                type="tool_result",
                tool_use_id=call_id,
                content=content,
                structured_content=structured_content,
                is_error=is_error,
            ),
            subagent_invocation_id=call.subagent_invocation_id,
        )
        await self._write(self._event(ToolReturnedEvent, "tool_returned", returned))

    # Subagents

    async def subagent_invoked(
        self,
        invocation_id: str,
        name: str,
        subagent_input: dict[str, JsonValue] | None = None,
        *,
        subagent_invocation_id: str | None = None,
    ) -> None:
        """Write `subagent_invoked`. When a tool call started the subagent, pass
        the call's `tool_call_id` as `invocation_id`; `subagent_input` then
        defaults to the call's input, and `subagent_invocation_id` to the call's."""
        self._check("subagent_invoked")
        if invocation_id in self._subagents:
            raise RecorderError(f"subagent_invoked: {invocation_id!r} was already used")
        call = self._calls.get(invocation_id)
        if call is not None:
            subagent_input = call.input if subagent_input is None else subagent_input
            subagent_invocation_id = subagent_invocation_id or call.subagent_invocation_id
        self._subagents[invocation_id] = _Subagent(
            name=name, parent=subagent_invocation_id, time=self._now()
        )
        invoked = SubagentInvoked(
            subagent_name=name,
            invocation_id=invocation_id,
            subagent_invocation_id=subagent_invocation_id,
            subagent_input=subagent_input or {},
        )
        await self._write(self._event(SubagentInvokedEvent, "subagent_invoked", invoked))

    async def subagent_returned(
        self,
        invocation_id: str,
        text: str,
        reason: StopReason = "converged",
        *,
        usage: SubagentUsage | None = None,
    ) -> None:
        """Write `subagent_returned`. `usage` is dropped when the subagent's
        responses were reported as events, so a supervisor doesn't count them
        twice."""
        self._check("subagent_returned")
        subagent = self._subagents.get(invocation_id)
        if subagent is None or subagent.reason is not None:
            state = "unknown" if subagent is None else "already returned"
            raise RecorderError(f"subagent_returned: subagent {invocation_id!r} is {state}")
        subagent.reason = reason
        if invocation_id in self._reported_responses:
            usage = None
        returned = SubagentReturned(
            subagent_name=subagent.name,
            invocation_id=invocation_id,
            subagent_invocation_id=subagent.parent,
            duration_ms=_ms(subagent.time, self._now()),
            subagent_reason=reason,
            subagent_result_text=text,
            subagent_usage=usage,
        )
        await self._write(self._event(SubagentReturnedEvent, "subagent_returned", returned))

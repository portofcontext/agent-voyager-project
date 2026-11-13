"""Record native runtime reports directly into an ATIF document.

Adapters own the loop. The Recorder owns response boundaries, tool links,
subagent documents, usage accounting, and publication of immutable snapshots.
"""

import json
import uuid
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from avp._artifacts import ArtifactCollection
from avp._base import TrajectorySink
from avp._recording import (
    _content,
    _content_metadata,
    _document,
    _metadata,
    _metrics,
    _observation,
    _remaining,
)
from avp.artifacts import Role
from avp.commission import Commission, ModelRef
from avp.descriptor import AgentDescriptor
from avp.reports import (
    ContentBlock,
    ErrorCode,
    ImageBlock,
    RunContext,
    StopReason,
    SubagentUsage,
    TextBlock,
    ToolUseBlock,
    Usage,
)
from avp.trajectory import Recording, Trajectory
from avp.utils.preflight import check_commission
from avp.utils.pricing import Prices, compute_cost, load_prices

ABANDONED_TEXT = "The run ended while the subagent was still running."
UNRETURNED_TEXT = "The run ended before the tool returned."
STOPPED_BEFORE_START_TEXT = "The run stopped before start."


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
    step: dict[str, Any] | None = None


@dataclass
class _Subagent:
    name: str
    parent: str | None
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
    waiting: list[Callable[[], None]] = field(default_factory=list)
    """Document updates that depend on this response."""
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
    """Publish a current ATIF snapshot after each completed runtime report."""

    def __init__(
        self,
        sink: TrajectorySink,
        *,
        run_id: str | None = None,
        prices: Prices | None = None,
        now: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._sink = sink
        self._prices = prices
        self._now = now or (lambda: datetime.now(UTC))
        self.run_id = run_id or (new_id or (lambda: str(uuid.uuid4())))()
        self._begun = False
        self._started: RunContext | None = None
        self.ended = False
        self._response: _Response | None = None
        self._calls: dict[str, _Call] = {}
        self._subagents: dict[str, _Subagent] = {}
        self._root = _document(self.run_id, f"{self.run_id}/root", "unknown", "unknown")
        self._documents = {None: self._root}
        self._delegations: dict[str, dict[str, Any]] = {}
        self._assets: dict[str, bytes] = {}
        self._artifacts = ArtifactCollection()

    def _time(self) -> str:
        return self._now().isoformat()

    async def _publish(self) -> None:
        self._root.finish()
        data = deepcopy(self._root.data)
        await self._sink(
            Recording(
                Trajectory.model_validate(data), self._assets.copy(), self._artifacts.files.copy()
            )
        )

    async def artifact(self, path: str, content: bytes, *, role: Role) -> None:
        """Capture a selected file; inputs are immutable and paths are run-relative."""
        self._check("artifact", started=False)
        self._artifacts.add(path, content, role)
        await self._publish()

    async def _write(self, update: Callable[[], None]) -> None:
        if self._response is not None:
            self._response.waiting.append(update)
        else:
            update()
            await self._publish()

    def _check(self, report: str, *, started: bool = True) -> None:
        if self.ended:
            raise RecorderError(f"{report}: the run has ended")
        if started and self._started is None:
            raise RecorderError(f"{report}: called before start")

    def _scope(self, invocation: str | None):
        if invocation not in self._documents:
            raise RecorderError(f"unknown subagent {invocation!r}")
        return self._documents[invocation]

    async def begin(self, received: JsonValue, descriptor: AgentDescriptor) -> Commission | None:
        """Validate the Commission and initialize the agent's ATIF document."""
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
            if isinstance(received, dict) and isinstance(received.get("run_id"), str):
                self.run_id = str(received["run_id"])
        self._root = _document(
            self.run_id, f"{self.run_id}/root", descriptor.agent_name, descriptor.agent_version
        )
        self._documents = {None: self._root}
        self._artifacts.begin(
            commission.model_dump(mode="json", exclude_none=True) if commission else None,
            descriptor.model_dump(mode="json", exclude_none=True),
        )
        self._root.step(self._time(), "system", "Run initialized.")
        if commission is not None:
            refusal = check_commission(commission, descriptor)
        if refusal is not None:
            await self.error("invalid_commission", refusal)
            return None
        await self._publish()
        return commission

    async def start(self, started: RunContext, *, meta: dict[str, JsonValue] | None = None) -> None:
        self._check("start", started=False)
        if self._started is not None:
            raise RecorderError("start: called twice")
        data = started.model_dump(mode="json", exclude_none=True)
        self._artifacts.effective(data)
        self._started = started
        root = self._root
        root.data["steps"] = []
        _metadata(root.data)["started_at"] = self._time()
        if meta:
            _metadata(root.data)["annotations"] = deepcopy(meta)
        agent = root.data["agent"]
        agent["model_name"] = started.model.id
        agent["extra"] = {"avp": {"provider": data["model"]["provider"]}}
        agent["tool_definitions"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "parameters": t["inputSchema"],
                    **({"description": t["description"]} if "description" in t else {}),
                },
                **(
                    {"extra": {"avp": _remaining(t, {"name", "description", "inputSchema"})}}
                    if _remaining(t, {"name", "description", "inputSchema"})
                    else {}
                ),
            }
            for t in data.get("tools", [])
        ]
        if started.system_prompt is not None:
            root.step(self._time(), "system", started.system_prompt)
        root.step(self._time(), "user", started.prompt)
        await self._publish()

    async def error(
        self, code: ErrorCode, message: str, *, subagent_invocation_id: str | None = None
    ) -> None:
        self._check("error", started=False)
        timestamp = self._time()

        def update():
            doc = self._scope(subagent_invocation_id)
            if self._started is None:
                doc.data["steps"] = []
                self.ended = True
                _metadata(doc.data).update(complete=True, stop_reason="error", stopped_at=timestamp)
            _metadata(doc.step(timestamp, "system", message))["error_code"] = code

        await self._write(update)

    async def stop(self, reason: StopReason, output: JsonValue = None) -> None:
        if self.ended:
            return
        if self._started is None:
            await self.error("agent_crash", STOPPED_BEFORE_START_TEXT)
            return
        await self.close_response()
        running = [id for id, child in self._subagents.items() if child.reason is None]
        for invocation in running:
            await self.subagent_returned(invocation, ABANDONED_TEXT, "abandoned")
        for call_id in [id for id, call in self._calls.items() if not call.returned]:
            await self.tool_returned(call_id, UNRETURNED_TEXT, is_error=True)
        if running and reason == "converged":
            reason = "abandoned"
        self.ended = True
        _metadata(self._root.data).update(
            complete=True, stop_reason=reason, stopped_at=self._time()
        )
        last_message = next(
            (
                step["message"]
                for step in reversed(self._root.data["steps"])
                if step["source"] == "agent"
            ),
            None,
        )
        if not (isinstance(output, str) and output == last_message) and (
            output is not None or last_message is not None
        ):
            _metadata(self._root.data)["output"] = output
        await self._publish()

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
        self._check("response")
        assert self._started is not None
        calls = [b for b in content if isinstance(b, ToolUseBlock)]
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
        self._scope(subagent_invocation_id)
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
        servers = {t.name: t.mcp_server_id for t in self._started.tools or []}
        for call in calls:
            self._calls[call.id] = _Call(
                call.name, call.input, servers.get(call.name), subagent_invocation_id, now
            )
            response.call_ids.add(call.id)
        if key is None:
            await self.close_response()

    async def usage(self, usage: UsageReport, *, key: str | None = None) -> None:
        self._check("usage")
        if self._response is None or (key is not None and key != self._response.key):
            raise RecorderError(f"usage: no open response with key {key!r}")
        self._response.usage = usage

    async def close_response(self) -> None:
        response = self._response
        if response is None:
            return
        self._response = None
        if _has_content(response.content):
            self._record_response(response)
        for update in response.waiting:
            update()
        await self._publish()

    def _record_response(self, response: _Response) -> None:
        report = response.usage
        usage: dict[str, Any] = {}
        if report is not None:
            if self._prices is None and report.cost_usd is None:
                self._prices = load_prices()
            cost, source = compute_cost(
                self._prices or Prices(fetched=self._now(), models={}),
                response.model,
                input_tokens=report.input_tokens,
                output_tokens=report.output_tokens,
                cache_read_input_tokens=report.cache_read_input_tokens or 0,
                cache_creation_input_tokens=report.cache_creation_input_tokens or 0,
                response_model=response.response_model,
                reported_cost_usd=report.cost_usd,
            )
            usage = Usage(
                **report.model_dump(exclude={"cost_usd"}), cost_usd=cost, cost_source=source
            ).model_dump(exclude_none=True)
        doc = self._scope(response.subagent_invocation_id)
        blocks = [b.model_dump(mode="json", exclude_none=True) for b in response.content]
        visible = [b for b in blocks if b["type"] in ("text", "image", "refusal")]
        step = doc.step(response.last.isoformat(), "agent", _content(visible, self._assets))
        step.update(
            llm_call_count=1,
            metrics=_metrics(usage),
        )
        doc.record_model(
            step,
            response.model.model_dump(exclude_none=True),
            response.response_model or response.model.id,
        )
        metadata = _metadata(step)
        metadata.update(
            duration_ms=response.duration_ms
            if response.duration_ms is not None
            else _ms(response.opened, response.last),
        )
        if response.finish_reasons:
            metadata["finish_reasons"] = response.finish_reasons
        if response.meta:
            metadata["annotations"] = response.meta
        if details := _content_metadata(visible):
            metadata["message_metadata"] = details
        reasoning = [
            b["thinking"] for b in blocks if b["type"] == "thinking" and not b.get("redacted")
        ]
        if reasoning:
            step["reasoning_content"] = "\n".join(reasoning)
        details, offset = [], 0
        for block in blocks:
            if block["type"] != "thinking":
                continue
            entry = _remaining(block, {"type", "thinking"})
            if block.get("redacted"):
                entry["encrypted_content"] = block["thinking"]
            elif entry:
                entry.update(start=offset, end=offset + len(block["thinking"]))
            if not block.get("redacted"):
                offset += len(block["thinking"]) + 1
            if entry:
                details.append(entry)
        if details:
            metadata["reasoning_metadata"] = details
        for block in blocks:
            if block["type"] in ("tool_use", "server_tool_use"):
                call = {
                    "tool_call_id": block["id"],
                    "function_name": block["name"],
                    "arguments": block["input"],
                }
                if block["type"] == "server_tool_use":
                    _metadata(call)["server_side"] = True
                if extra := _remaining(block, {"type", "id", "name", "input"}):
                    _metadata(call)["provider_metadata"] = extra
                if block["type"] == "tool_use":
                    state = self._calls[block["id"]]
                    state.step = step
                    _metadata(call)["started_at"] = state.time.isoformat()
                    declared_server = next(
                        (
                            t.get("extra", {}).get("avp", {}).get("mcp_server_id")
                            for t in doc.data["agent"].get("tool_definitions", [])
                            if t["function"]["name"] == block["name"]
                        ),
                        None,
                    )
                    if state.mcp_server_id and state.mcp_server_id != declared_server:
                        _metadata(call)["mcp_server_id"] = state.mcp_server_id
                step.setdefault("tool_calls", []).append(call)
        for block in blocks:
            if block["type"] in ("tool_result", "server_tool_result"):
                self._result(
                    step,
                    block["tool_use_id"],
                    block["content"],
                    response.last.isoformat(),
                    block.get("is_error", False),
                    provider_metadata=_remaining(
                        block, {"type", "tool_use_id", "name", "content", "is_error"}
                    ),
                )
        doc.usages.append(usage)

    def _result(self, step, call_id, content, timestamp, is_error=False, **details):
        if not any(c["tool_call_id"] == call_id for c in step.get("tool_calls", [])):
            raise RecorderError(f"unmatched tool result {call_id!r}")
        result = _observation(step, call_id)
        result.update(
            content=_content(content, self._assets),
            extra={
                "avp": {
                    "finished_at": timestamp,
                    "is_error": bool(is_error),
                    **{k: v for k, v in details.items() if v is not None and v != {}},
                }
            },
        )
        if annotations := _content_metadata(content):
            _metadata(result)["content_metadata"] = annotations

    async def tool_returned(
        self,
        call_id: str,
        content: str | list[TextBlock | ImageBlock],
        *,
        is_error: bool | None = None,
        structured_content: dict[str, JsonValue] | None = None,
    ) -> None:
        self._check("tool_returned")
        call = self._calls.get(call_id)
        if call is None or call.returned:
            raise RecorderError(
                f"tool_returned: tool call {call_id!r} is {'unknown' if call is None else 'already returned'}"
            )
        call.returned = True
        child = self._subagents.get(call_id)
        if child is not None and child.reason is not None:
            is_error = child.reason != "converged"
        if self._response is not None and call_id in self._response.call_ids:
            self._response.tool_returned = True
        timestamp = self._time()
        raw = (
            content
            if isinstance(content, str)
            else [b.model_dump(mode="json", exclude_none=True) for b in content]
        )

        def update():
            if call.step is None:
                raise RecorderError(f"tool_returned: {call_id!r} has no response")
            self._result(
                call.step,
                call_id,
                raw,
                timestamp,
                is_error,
                structured_content=structured_content,
            )

        await self._write(update)

    async def subagent_invoked(
        self,
        invocation_id: str,
        name: str,
        subagent_input: dict[str, JsonValue] | None = None,
        *,
        subagent_invocation_id: str | None = None,
    ) -> None:
        self._check("subagent_invoked")
        if invocation_id in self._subagents:
            raise RecorderError(f"subagent_invoked: {invocation_id!r} was already used")
        call = self._calls.get(invocation_id)
        if call:
            subagent_input = call.input if subagent_input is None else subagent_input
            subagent_invocation_id = subagent_invocation_id or call.subagent_invocation_id
        self._subagents[invocation_id] = _Subagent(name, subagent_invocation_id)
        timestamp = self._time()

        def update():
            parent = self._scope(subagent_invocation_id)
            child = _document(
                self.run_id, f"{self.run_id}/subagent/{invocation_id}", name, "unknown"
            )
            self._documents[invocation_id] = child
            parent.children.append(child)
            parent.data.setdefault("subagent_trajectories", []).append(child.data)
            _metadata(child.data)["started_at"] = timestamp
            child.step(timestamp, "user", json.dumps(subagent_input or {}, ensure_ascii=False))
            step = call.step if call else None
            result = (
                _observation(step, invocation_id)
                if step is not None
                else _observation(parent.step(timestamp, "system", f"Delegated to {name}."), None)
            )
            result["subagent_trajectory_ref"] = [{"trajectory_id": child.data["trajectory_id"]}]
            self._delegations[invocation_id] = result

        await self._write(update)

    async def subagent_returned(
        self,
        invocation_id: str,
        text: str,
        reason: StopReason = "converged",
        *,
        usage: SubagentUsage | None = None,
    ) -> None:
        self._check("subagent_returned")
        child = self._subagents.get(invocation_id)
        if child is None or child.reason is not None:
            raise RecorderError(
                f"subagent_returned: subagent {invocation_id!r} is {'unknown' if child is None else 'already returned'}"
            )
        child.reason = reason
        timestamp = self._time()

        def update():
            doc = self._scope(invocation_id)
            _metadata(doc.data).update(complete=True, stop_reason=reason, stopped_at=timestamp)
            self._delegations[invocation_id].setdefault("content", text)
            if not doc.usages:
                counts = usage.model_dump(exclude_none=True) if usage else {}
                doc.usages.append(counts)
                if details := _metrics(counts).get("extra", {}).get("avp", {}):
                    _metadata(doc.data)["usage_details"] = details

        await self._write(update)

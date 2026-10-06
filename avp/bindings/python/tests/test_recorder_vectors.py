"""Run the shared recorder vectors against the Python `Recorder`.

Each vector under `avp/core/conformance/src/avp_conformance/recorder/v0.1/`
is a script of Recorder calls plus the NDJSON events they must produce under
a fixed clock, compared after id normalization (see that directory's README). The Rust and
TypeScript bindings run the same files.

Regenerate `expected` after an intentional rule change with
`AVP_UPDATE_RECORDER_VECTORS=1 uv run pytest avp/bindings/python/tests/test_recorder_vectors.py`,
then review the diff: the vectors are the contract.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from avp.commission import Commission
from avp.content import AVPContentBlock, ToolResultBlock
from avp.descriptor import AgentDescriptor, McpServerDecl, SkillDecl, SubagentDecl, ToolDecl
from avp.pricing import ModelPrice
from avp.recorder import Recorder
from avp.sink import _serialize
from avp.trajectory import ErrorCode, Event, StopReason, SubagentUsage, Usage

VECTORS = Path(__file__).resolve().parents[3] / "core/conformance/src/avp_conformance/recorder/v0.1"
UPDATE = os.environ.get("AVP_UPDATE_RECORDER_VECTORS") == "1"
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
TRACE_ID = "0af7651916cd43dd8448eb211c80319c"

_content = TypeAdapter(list[AVPContentBlock])


class VectorClock:
    """Time stands still between calls; the runner sets it from each call's `t` (ms)."""

    t_ms = 0

    def now_iso(self) -> str:
        at = EPOCH + timedelta(milliseconds=self.t_ms)
        return at.strftime("%Y-%m-%dT%H:%M:%S.") + f"{at.microsecond // 1000:03d}Z"

    def monotonic(self) -> float:
        return self.t_ms / 1000


class VectorIds:
    def __init__(self) -> None:
        self.spans = 0
        self.events = 0

    def trace_id(self) -> str:
        return TRACE_ID

    def span_id(self) -> str:
        self.spans += 1
        return f"{self.spans:016x}"

    def event_id(self) -> str:
        self.events += 1
        return f"evt-{self.events}"


def _decls(model: Any, items: list[dict[str, Any]] | None) -> list[Any] | None:
    return None if items is None else [model.model_validate(i) for i in items]


async def _apply(rec: Recorder, op: str, a: dict[str, Any]) -> None:
    if op == "prelude":
        commission = a.get("commission")
        await rec.prelude(
            Commission.model_validate(commission) if commission is not None else None,
            AgentDescriptor.model_validate(a["descriptor"]),
        )
    elif op == "start":
        await rec.start(
            request_model=a.get("request_model"),
            prompt=a.get("prompt"),
            system_prompt=a.get("system_prompt"),
            tools=_decls(ToolDecl, a.get("tools")),
            mcp_servers=_decls(McpServerDecl, a.get("mcp_servers")),
            skills=_decls(SkillDecl, a.get("skills")),
            subagents=_decls(SubagentDecl, a.get("subagents")),
            session_id=a.get("session_id"),
            thread_id=a.get("thread_id"),
            tags=a.get("tags"),
            meta=a.get("meta"),
        )
    elif op == "assistant":
        usage = a.get("usage")
        await rec.assistant(
            _content.validate_python(a["content"]),
            Usage.model_validate(usage) if usage is not None else None,
            model=a.get("model"),
            request_model=a.get("request_model"),
            turn_key=a.get("turn_key"),
            finish_reasons=a.get("finish_reasons"),
            meta=a.get("meta"),
            cost_usd=a.get("cost_usd"),
            duration_ms=a.get("duration_ms"),
        )
    elif op == "usage":
        await rec.usage(
            Usage.model_validate(a["usage"]),
            turn_key=a.get("turn_key"),
            cost_usd=a.get("cost_usd"),
            duration_ms=a.get("duration_ms"),
        )
    elif op == "close_turn":
        await rec.close_turn()
    elif op == "tool_result":
        content = a["content"]
        await rec.tool_result(
            a["call_id"],
            ToolResultBlock.model_validate(content) if isinstance(content, dict) else content,
            is_error=a.get("is_error", False),
            structured_content=a.get("structured_content"),
        )
    elif op == "subagent_start":
        await rec.subagent_start(
            a["invocation_id"], a["name"], a.get("input"), description=a.get("description")
        )
    elif op == "subagent_result":
        usage = a.get("usage")
        await rec.subagent_result(
            a["invocation_id"],
            a["text"],
            StopReason(a.get("reason", "converged")),
            usage=SubagentUsage.model_validate(usage) if usage is not None else None,
            structured=a.get("structured"),
        )
    elif op == "error":
        await rec.error(ErrorCode(a["code"]), a["message"])
    elif op == "stop":
        await rec.stop(StopReason(a["reason"]), a.get("output"))
    else:
        raise ValueError(f"unknown recorder op {op!r}")


async def _run(vector: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[Event] = []

    async def sink(event: Event) -> None:
        events.append(event)

    cfg = vector.get("recorder", {})
    clock = VectorClock()
    rec = Recorder(
        sink,
        run_id=cfg["run_id"],
        provider=cfg.get("provider"),
        prices={m: ModelPrice.model_validate(p) for m, p in cfg.get("prices", {}).items()},
        clock=clock,
        ids=VectorIds(),
    )
    for call in vector["calls"]:
        clock.t_ms = call["t"]
        args = {k: v for k, v in call.items() if k not in ("t", "op")}
        await _apply(rec, call["op"], args)
    return [json.loads(_serialize(e)) for e in events]


def normalize(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rename event ids and span ids by order of first appearance on the wire
    (`evt-1`, `span-1`, ...; the zero parent stays). Which id a binding mints
    first is an implementation detail; the span tree is the contract."""
    names: dict[str, str] = {}

    def name(value: str, prefix: str) -> str:
        if value == "0" * 16:
            return value
        if value not in names:
            names[value] = f"{prefix}-{sum(n.startswith(prefix) for n in names.values()) + 1}"
        return names[value]

    out = []
    for event in events:
        event = json.loads(json.dumps(event))
        event["id"] = name(event["id"], "evt")
        data = event["data"]
        data["span_id"] = name(data["span_id"], "span")
        data["parent_span_id"] = name(data["parent_span_id"], "span")
        out.append(event)
    return out


def _paths() -> list[Path]:
    return sorted(VECTORS.glob("*.json"))


@pytest.mark.parametrize("path", _paths(), ids=lambda p: p.stem)
def test_recorder_vector(path: Path) -> None:
    vector = json.loads(path.read_text())
    actual = normalize(asyncio.run(_run(vector)))
    if UPDATE:
        vector["expected"] = actual
        path.write_text(json.dumps(vector, indent=2) + "\n")
        return
    expected = vector["expected"]
    assert [e["type"] for e in actual] == [e["type"] for e in expected]
    for i, (got, want) in enumerate(zip(actual, expected, strict=True)):
        assert got == want, f"event {i} ({want['type']}) differs"


def test_vectors_exist() -> None:
    assert len(_paths()) >= 10

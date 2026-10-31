"""The shared Recorder cases in `avp_sdk/testdata/recorder/`, which every SDK's
Recorder passes. See the README there for the format."""

import asyncio
import itertools
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from avp.commission import ModelRef
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder, RecorderError, UsageReport
from avp.trajectory import AgentStarted, ContentBlock, Event, SubagentUsage
from avp.utils.pricing import Prices

CASES = Path(__file__).resolve().parents[2] / "testdata" / "recorder"
START = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT = TypeAdapter(list[ContentBlock])


async def _call(rec: Recorder, call: dict[str, Any]) -> None:
    name = call["call"]
    usage = (
        UsageReport.model_validate(call["usage"])
        if call.get("usage") and name in ("response", "usage")
        else None
    )
    if name == "begin":
        descriptor = AgentDescriptor.model_validate(call["descriptor"])
        await rec.begin(call["received"], descriptor)
    elif name == "start":
        await rec.start(AgentStarted.model_validate(call["started"]))
    elif name == "response":
        await rec.response(
            CONTENT.validate_python(call["content"]),
            usage=usage,
            model=ModelRef.model_validate(call["model"]) if "model" in call else None,
            response_model=call.get("response_model"),
            finish_reasons=call.get("finish_reasons"),
            duration_ms=call.get("duration_ms"),
            subagent_invocation_id=call.get("subagent_invocation_id"),
            key=call.get("key"),
        )
    elif name == "usage":
        assert usage is not None
        await rec.usage(usage, key=call.get("key"))
    elif name == "close_response":
        await rec.close_response()
    elif name == "tool_returned":
        await rec.tool_returned(call["call_id"], call["content"], is_error=call.get("is_error"))
    elif name == "subagent_invoked":
        await rec.subagent_invoked(call["invocation_id"], call["name"], call.get("subagent_input"))
    elif name == "subagent_returned":
        subagent_usage = call.get("usage")
        await rec.subagent_returned(
            call["invocation_id"],
            call["text"],
            call.get("reason", "converged"),
            usage=SubagentUsage.model_validate(subagent_usage) if subagent_usage else None,
        )
    elif name == "error":
        await rec.error(call["code"], call["message"])
    elif name == "stop":
        await rec.stop(call["reason"], call.get("output"))
    else:
        raise AssertionError(f"unknown call {name!r}")


def run_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    """The events the Recorder writes for the case's calls, each with `t` (ms
    since the start) in place of `time` and without `id`."""
    events: list[Event] = []
    clock = [START]
    counter = itertools.count(1)

    async def sink(event: Event) -> None:
        events.append(event)

    rec = Recorder(
        sink,
        run_id="run-0",
        prices=Prices(fetched=START, models=case.get("prices", {})),
        now=lambda: clock[0],
        new_id=lambda: f"event-{next(counter)}",
    )

    async def calls() -> None:
        for call in case["calls"]:
            clock[0] = START + timedelta(milliseconds=call["t"])
            written = len(events)
            if call.get("raises"):
                with pytest.raises(RecorderError):
                    await _call(rec, call)
                assert len(events) == written, f"a rejected {call['call']} wrote events"
            else:
                await _call(rec, call)

    asyncio.run(calls())
    ids = [event.id for event in events]
    assert len(set(ids)) == len(ids), "two events share an id"
    out = []
    for event in events:
        dumped = event.model_dump(mode="json", exclude_none=True, by_alias=True)
        del dumped["id"]
        dumped["t"] = round((event.time - START).total_seconds() * 1000)
        del dumped["time"]
        out.append(dumped)
    return out


def _same(actual: Any, expected: Any, where: str = "") -> None:
    if expected == "<any>":
        assert isinstance(actual, str), where
    elif isinstance(expected, float) or isinstance(actual, float):
        assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12), where
    elif isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), where
        for key in expected:
            _same(actual[key], expected[key], f"{where}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), where
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _same(a, e, f"{where}[{i}]")
    else:
        assert actual == expected, where


@pytest.mark.parametrize("path", sorted(CASES.glob("*.json")), ids=lambda path: path.stem)
def test_case(path: Path) -> None:
    case = json.loads(path.read_text())
    actual = run_case(case)
    assert [e["type"] for e in actual] == [e["type"] for e in case["events"]]
    _same(actual, case["events"], "events")

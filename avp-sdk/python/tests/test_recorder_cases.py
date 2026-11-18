"""The shared Recorder cases in `avp-sdk/testdata/recorder/`, which every SDK's
Recorder passes. See the README there for the format."""

import asyncio
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from avp.descriptor import AgentDescriptor
from avp.recorder import Part, Recorder, RecorderError, Usage
from avp.trajectory import Agent, FinalMetrics, Recording, final_output, parse_trajectory
from avp.utils.pricing import Prices

CASES = Path(__file__).resolve().parents[2] / "testdata" / "recorder"
START = datetime(2026, 1, 1, tzinfo=UTC)
PARTS = TypeAdapter(list[Part])


async def _call(rec: Recorder, call: dict[str, Any]) -> None:
    name = call["call"]
    if name == "begin":
        await rec.begin(call["received"], AgentDescriptor.model_validate(call["descriptor"]))
    elif name == "start":
        await rec.start(
            Agent.model_validate(call["agent"]),
            call["prompt"],
            system_prompt=call.get("system_prompt"),
        )
    elif name == "step":
        await rec.step(
            PARTS.validate_python(call["parts"]),
            usage=Usage.model_validate(call["usage"]) if "usage" in call else None,
            model_name=call.get("model_name"),
            finish_reasons=call.get("finish_reasons"),
            subagent=call.get("subagent"),
        )
    elif name == "result":
        await rec.result(
            call["call_id"],
            call["content"],
            is_error=call.get("is_error", False),
            structured_content=call.get("structured_content"),
        )
    elif name == "subagent_started":
        await rec.subagent_started(call["call_id"], call["name"], call["prompt"])
    elif name == "subagent_stopped":
        final_metrics = call.get("final_metrics")
        await rec.subagent_stopped(
            call["call_id"],
            call.get("reason", "converged"),
            final_metrics=FinalMetrics.model_validate(final_metrics) if final_metrics else None,
        )
    elif name == "error":
        await rec.error(call["code"], call["message"], subagent=call.get("subagent"))
    elif name == "stop":
        await rec.stop(call["reason"], call.get("output"))
    else:
        raise AssertionError(f"unknown call {name!r}")


def run_case(case: dict[str, Any]) -> Recording:
    """Make the case's calls and return the one Recording written."""
    written: list[Recording] = []
    clock = [START]

    async def sink(recording: Recording) -> None:
        written.append(recording)

    rec = Recorder(
        sink,
        run_id="run-0",
        prices=Prices(fetched=START, models=case.get("prices", {})),
        now=lambda: clock[0],
    )

    async def calls() -> None:
        for call in case["calls"]:
            clock[0] = START + timedelta(milliseconds=call["t"])
            if call.get("raises"):
                with pytest.raises(RecorderError):
                    await _call(rec, call)
            else:
                await _call(rec, call)

    asyncio.run(calls())
    assert len(written) == 1, f"the Recorder wrote {len(written)} documents, not 1"
    return written[0]


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
    elif isinstance(expected, str) and expected.startswith("2026-01-01T"):
        assert datetime.fromisoformat(actual) == datetime.fromisoformat(expected), where
    else:
        assert actual == expected, where


@pytest.mark.parametrize("path", sorted(CASES.glob("*.json")), ids=lambda path: path.stem)
def test_case(path: Path) -> None:
    case = json.loads(path.read_text())
    recording = run_case(case)
    actual = json.loads(recording.json())
    _same(actual, case["trajectory"], "trajectory")
    assert sorted(recording.assets) == sorted(case.get("files", []))
    stop = next((c for c in reversed(case["calls"]) if c["call"] == "stop"), None)
    if stop and actual["extra"]["avp"].get("started_at"):
        assert final_output(parse_trajectory(actual)) == stop.get("output")

"""Native recording, independent ATIF input, and durable document publication."""

import asyncio
import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from avp.commission import ModelRef
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder, UsageReport
from avp.reports import (
    ImageBlock,
    RunContext,
    Source,
    SubagentUsage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from avp.trajectory import avp_metadata, parse_trajectory

DATA = Path(__file__).resolve().parents[2] / "testdata/atif"
MODEL = ModelRef(provider="test", id="model")


def test_upstream_terminus_document_reads_without_avp_metadata():
    raw = json.loads((DATA / "external-terminus.json").read_text())
    trajectory = parse_trajectory(raw)
    assert trajectory.agent.name == raw["agent"]["name"]
    assert len(trajectory.steps) == len(raw["steps"])
    assert avp_metadata(trajectory) == {}
    assert parse_trajectory(trajectory.model_dump_json()).steps == trajectory.steps


def test_native_tools_images_reasoning_and_partial_snapshots(tmp_path):
    snapshots = []
    image = ImageBlock(
        type="image",
        source=Source(
            type="base64", media_type="image/png", data=base64.b64encode(b"image fixture").decode()
        ),
    )

    async def run():
        async def sink(snapshot):
            snapshots.append(snapshot)
            snapshot.write(tmp_path / "trajectory.json")
            assert (
                parse_trajectory((tmp_path / "trajectory.json").read_text()) == snapshot.trajectory
            )

        rec = Recorder(sink, run_id="test")
        await rec.start(RunContext(prompt="hello", model=MODEL))
        await rec.response(
            [
                ThinkingBlock(type="thinking", thinking="reason", signature="sig"),
                image,
                ToolUseBlock(type="tool_use", id="call", name="echo", input={}),
            ],
            usage=UsageReport(input_tokens=10, output_tokens=4, cost_usd=0.1),
        )
        await rec.tool_returned(
            "call", [image, TextBlock(type="text", text="ok")], structured_content={"ok": True}
        )
        await rec.stop("converged", {"ok": True})

    asyncio.run(run())
    pending = snapshots[1].trajectory.steps[-1]
    assert pending.tool_calls[0].tool_call_id == "call" and pending.observation is None
    assert not avp_metadata(snapshots[1].trajectory)["complete"]
    final = snapshots[-1]
    step = final.trajectory.steps[-1]
    assert step.reasoning_content == "reason"
    assert avp_metadata(step)["reasoning_metadata"][0]["signature"] == "sig"
    result = step.observation.results[0]
    assert result.source_call_id == "call" and avp_metadata(result)["structured_content"] == {
        "ok": True
    }
    assert len(final.assets) == 1
    assert len(list((tmp_path / "images").iterdir())) == 1
    assert final.trajectory.final_metrics.total_prompt_tokens == 10
    assert avp_metadata(final.trajectory)["output"] == {"ok": True}
    assert not list(tmp_path.glob(".trajectory.json.*"))


@pytest.mark.parametrize("reported", [False, True])
def test_opaque_child_uses_aggregate_only_when_no_child_responses(reported):
    snapshots = []

    async def run():
        async def sink(s):
            snapshots.append(s)

        rec = Recorder(sink, run_id="child")
        await rec.start(RunContext(prompt="go", model=MODEL))
        await rec.response(
            [ToolUseBlock(type="tool_use", id="child", name="delegate", input={})],
            usage=UsageReport(input_tokens=10, output_tokens=2, cost_usd=0.1),
        )
        await rec.subagent_invoked("child", "helper")
        if reported:
            await rec.response(
                [TextBlock(type="text", text="done")],
                subagent_invocation_id="child",
                usage=UsageReport(input_tokens=20, output_tokens=3, cost_usd=0.2),
            )
        await rec.subagent_returned(
            "child",
            "done",
            usage=SubagentUsage(
                input_tokens=20, output_tokens=3, cost_usd=0.2, cost_source="reported"
            ),
        )
        await rec.tool_returned("child", "done")
        await rec.stop("converged")

    asyncio.run(run())
    root = snapshots[-1].trajectory
    assert root.final_metrics.total_prompt_tokens == 30
    assert root.final_metrics.total_completion_tokens == 5
    assert root.final_metrics.total_cost_usd == pytest.approx(0.3)
    assert len(root.subagent_trajectories[0].steps) == (2 if reported else 1)


def test_unknown_usage_is_not_zero_and_abandoned_work_is_closed():
    snapshots = []

    async def run():
        async def sink(s):
            snapshots.append(s)

        rec = Recorder(sink)
        await rec.start(RunContext(prompt="go", model=MODEL))
        await rec.response([ToolUseBlock(type="tool_use", id="c", name="delegate", input={})])
        await rec.subagent_invoked("c", "helper")
        await rec.stop("converged")

    asyncio.run(run())
    root = snapshots[-1].trajectory
    assert avp_metadata(root)["stop_reason"] == "abandoned"
    assert root.final_metrics.total_prompt_tokens is None
    assert avp_metadata(root.steps[-1].observation.results[0])["is_error"]


def test_secret_commission_is_not_embedded_in_the_document():
    snapshots = []

    async def run():
        async def sink(s):
            snapshots.append(s)

        rec = Recorder(sink)
        await rec.begin(
            {
                "avp_version": "0.1",
                "run_id": "r",
                "prompt": "hi",
                "model": {"provider": "test", "id": "m", "credential": {"env": "SECRET_NAME"}},
            },
            AgentDescriptor(avp_version="0.1", agent_name="test", agent_version="1"),
        )
        await rec.stop("error")

    asyncio.run(run())
    assert "SECRET_NAME" not in snapshots[-1].trajectory.model_dump_json()


def test_invalid_call_references_fail_upstream_validation():
    with pytest.raises(ValidationError):
        parse_trajectory(
            {
                "schema_version": "ATIF-v1.8",
                "agent": {"name": "other", "version": "1"},
                "steps": [
                    {
                        "step_id": 1,
                        "source": "agent",
                        "message": "",
                        "observation": {
                            "results": [{"source_call_id": "missing", "content": "bad"}]
                        },
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "case",
    json.loads((Path(__file__).parents[2] / "testdata/atif/validation.json").read_text()),
    ids=lambda case: case["name"],
)
def test_upstream_semantics(case):
    if case["valid"]:
        parse_trajectory(case["trajectory"])
    else:
        with pytest.raises(ValueError):
            parse_trajectory(case["trajectory"])

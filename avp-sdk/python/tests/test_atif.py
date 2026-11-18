"""Recording runs, reading ATIF from other producers, and writing documents."""

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from avp.agent_cli import trajectory_sink
from avp.descriptor import AgentDescriptor
from avp.recorder import Call, Recorder, Text, Usage
from avp.trajectory import (
    Agent,
    Recording,
    avp_metadata,
    final_output,
    parse_trajectory,
)

DATA = Path(__file__).resolve().parents[2] / "testdata/atif"
DESCRIPTOR = AgentDescriptor(avp_version="0.1", agent_name="test", agent_version="1")
AGENT = Agent(
    name="test", version="1", model_name="model", extra={"avp": {"model": {"provider": "test"}}}
)


def record(steps):
    """Run `steps(rec)` and return the one Recording written."""
    written = []

    async def run():
        async def sink(recording):
            written.append(recording)

        rec = Recorder(sink, run_id="test")
        await rec.begin(None, DESCRIPTOR)
        await rec.start(AGENT, "go")
        await steps(rec)

    asyncio.run(run())
    assert len(written) == 1
    return written[0]


@pytest.mark.parametrize("mask, expected", [(0o022, 0o644), (0o077, 0o600)])
def test_writes_respect_normal_file_creation_permissions(tmp_path, mask, expected):
    recording = Recording(parse_trajectory((DATA / "external-terminus.json").read_text()))
    path = tmp_path / "trajectory.json"
    previous = os.umask(mask)
    try:
        for _ in range(2):
            recording.write(path)
            assert stat.S_IMODE(path.stat().st_mode) == expected
            assert parse_trajectory(path.read_text()) == recording.trajectory
    finally:
        os.umask(previous)


def test_upstream_terminus_document_reads_without_avp_metadata():
    raw = json.loads((DATA / "external-terminus.json").read_text())
    trajectory = parse_trajectory(raw)
    assert trajectory.agent.name == raw["agent"]["name"]
    assert len(trajectory.steps) == len(raw["steps"])
    assert avp_metadata(trajectory) == {}
    assert parse_trajectory(trajectory.model_dump_json()).steps == trajectory.steps


def test_images_are_files_beside_the_trajectory(tmp_path):
    async def steps(rec):
        image = rec.image(b"image fixture", "image/png")
        await rec.step([image, Call(id="c", name="look", arguments={})])
        await rec.result("c", [image])
        await rec.stop("converged", {"ok": True})

    recording = record(steps)
    (name,) = recording.assets
    assert recording.trajectory.steps[-1].message[0].source.path == name
    recording.write(tmp_path / "trajectory.json")
    assert (tmp_path / name).read_bytes() == b"image fixture"
    assert parse_trajectory((tmp_path / "trajectory.json").read_text()) == recording.trajectory
    assert not list(tmp_path.glob(".trajectory.json.*"))
    with pytest.raises(ValueError, match="--out"):
        asyncio.run(trajectory_sink(None)(recording))


@pytest.mark.parametrize("hidden", [True, False])
def test_reported_subagent_totals_count_only_when_its_responses_are_hidden(hidden):
    async def steps(rec):
        await rec.step(
            [Call(id="child", name="delegate", arguments={})],
            usage=Usage(prompt_tokens=10, completion_tokens=2, cost_usd=0.1),
        )
        await rec.subagent_started("child", "helper", "go")
        if not hidden:
            await rec.step(
                [Text(text="done")],
                subagent="child",
                usage=Usage(prompt_tokens=20, completion_tokens=3, cost_usd=0.2),
            )
        totals = Usage(prompt_tokens=20, completion_tokens=3, cost_usd=0.2)
        await rec.subagent_stopped("child", usage=totals)
        await rec.result("child", "done")
        await rec.stop("converged")

    root = record(steps).trajectory
    assert root.final_metrics.total_prompt_tokens == 30
    assert root.final_metrics.total_completion_tokens == 5
    assert root.final_metrics.total_cost_usd == pytest.approx(0.3)
    assert len(root.subagent_trajectories[0].steps) == (1 if hidden else 2)


def test_secret_values_are_not_in_the_document(monkeypatch):
    monkeypatch.setenv("TEST_SECRET", "s3cret-value")
    written = []

    async def run():
        async def sink(recording):
            written.append(recording)

        rec = Recorder(sink)
        commission = {
            "avp_version": "0.1",
            "run_id": "r",
            "prompt": "hi",
            "model": {"provider": "test", "id": "m", "credential": {"env": "TEST_SECRET"}},
        }
        await rec.begin(commission, DESCRIPTOR)
        await rec.stop("error")

    asyncio.run(run())
    assert "s3cret-value" not in written[0].json()


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


def test_nested_subagents_are_referenced_by_their_parents_and_counted_once():
    usage = Usage(prompt_tokens=10, completion_tokens=2)

    async def steps(rec):
        await rec.step([Call(id="outer", name="delegate", arguments={})], usage=usage)
        await rec.subagent_started("outer", "researcher", "look")
        inner = Call(id="inner", name="delegate", arguments={})
        await rec.step([inner], usage=usage, subagent="outer")
        await rec.subagent_started("inner", "helper", "look closer")
        await rec.step([Text(text="inner done")], usage=usage, subagent="inner")
        await rec.subagent_stopped("inner")
        await rec.result("inner", "inner done")
        await rec.step([Text(text="outer done")], usage=usage, subagent="outer")
        await rec.subagent_stopped("outer")
        await rec.result("outer", "outer done")
        await rec.step([Text(text="done")], usage=usage)
        await rec.stop("converged", "done")

    root = record(steps).trajectory
    child = root.subagent_trajectories[0]
    grandchild = child.subagent_trajectories[0]
    assert root.final_metrics.total_prompt_tokens == 50
    assert child.final_metrics.total_prompt_tokens == 30
    assert grandchild.final_metrics.total_prompt_tokens == 10
    for parent, delegated in [(root, child), (child, grandchild)]:
        references = [
            ref.trajectory_id
            for step in parent.steps
            if step.observation
            for result in step.observation.results
            for ref in result.subagent_trajectory_ref or []
        ]
        assert references == [delegated.trajectory_id]


@pytest.mark.parametrize("output", [None, False, 0, "", {"answer": 42}])
def test_final_output_prefers_extra_avp_output(output):
    raw = json.loads((DATA / "external-terminus.json").read_text())
    raw["steps"][-1]["source"] = "agent"
    raw["steps"][-1]["message"] = "42"
    assert final_output(parse_trajectory(raw)) == "42"
    raw["extra"] = {
        "avp": {
            "avp_version": "0.1",
            "stopped_at": "2026-01-01T00:00:00Z",
            "stop_reason": "converged",
            "output": output,
        }
    }
    assert final_output(parse_trajectory(raw)) == output

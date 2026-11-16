"""Four saved documents and complete, immutable start configuration."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from avp.agent_start import AgentStart, capture_start
from avp.commission import Commission, ModelRef
from avp.descriptor import AgentDescriptor, Skill, Subagent
from avp.recorder import Recorder
from avp.reports import ImageBlock, RunContext, Source, TextBlock

CASES = Path(__file__).parents[2] / "testdata/agent-start.json"
SCHEMA = Path(__file__).parents[3] / "spec/v0.1/agent-start.schema.json"


@pytest.mark.parametrize("case", json.loads(CASES.read_text()), ids=lambda c: c["name"])
def test_shared_start_schema(case):
    validator = Draft202012Validator(json.loads(SCHEMA.read_text()))
    assert validator.is_valid(case["document"]) == case["valid"]
    if case["valid"]:
        AgentStart.model_validate(case["document"])
    else:
        with pytest.raises(ValueError):
            AgentStart.model_validate(case["document"])


def test_four_documents_reference_immutable_skill_files(tmp_path):
    skill = tmp_path / "native-skill"
    skill.mkdir()
    original = "---\nname: research\ndescription: Research.\n---\nRead references.\r\n"
    (skill / "SKILL.md").write_bytes(original.encode())
    (skill / "references").mkdir()
    binary = b"\x00\xff\r\n"
    (skill / "references/data.bin").write_bytes(binary)
    out = tmp_path / "run/trajectory.json"
    snapshots = []
    commission: dict[str, Any] = {
        "avp_version": "0.1",
        "run_id": "r",
        "prompt": "research",
        "model": {"provider": "test", "id": "requested"},
        "mcp_servers": [{"id": "math", "type": "stdio", "command": ["math-server"]}],
        "output_schema": {"type": "object"},
    }

    out.parent.mkdir()
    supplied_json = {**commission, "system_prompt": None}
    (out.parent / "commission.json").write_text(json.dumps(supplied_json))

    async def run():
        async def sink(snapshot):
            snapshot.write(out)
            snapshots.append(snapshot)

        rec = Recorder(sink, run_id="r")
        await rec.begin(
            commission, AgentDescriptor(avp_version="0.1", agent_name="test", agent_version="1")
        )
        assert not (out.parent / "agent-start.json").exists()
        await rec.start(
            RunContext(
                prompt="research",
                system_prompt="",
                model=ModelRef(provider="test", id="resolved"),
                skills=[Skill(name="research", description="Research.", source=skill.as_uri())],
                subagents=[
                    Subagent(
                        name="child",
                        skills=[
                            Skill(name="research", description="Research.", source=skill.as_uri())
                        ],
                    )
                ],
                mcp_servers=[{"id": "math", "status": "connected"}],
            )
        )
        (skill / "SKILL.md").write_text("changed during the run")
        await rec.response(
            [
                TextBlock(
                    type="text",
                    text="42",
                    citations=[{"type": "url", "source_url": "https://example.com"}],
                )
            ]
        )
        await rec.stop("converged", {"answer": 42})

    asyncio.run(run())
    assert {p.name for p in out.parent.iterdir()} == {
        "commission.json",
        "descriptor.json",
        "agent-start.json",
        "trajectory.json",
        "skills",
    }
    started = AgentStart.model_validate_json((out.parent / "agent-start.json").read_bytes())
    assert started.model.id == "resolved"
    assert started.system_prompt == ""
    assert started.output_schema == {"type": "object"}
    assert started.skills and started.skills[0].path
    assert started.subagents and started.subagents[0].skills
    assert started.mcp_servers
    assert started.skills[0].path == "skills/0-research"
    captured = out.parent / started.skills[0].path
    assert (captured / "SKILL.md").read_bytes() == original.encode()
    assert (captured / "references/data.bin").read_bytes() == binary
    child = started.subagents[0].skills[0]
    assert child.path == "skills/subagent-0/0-research"
    assert (out.parent / child.path / "references/data.bin").read_bytes() == binary
    assert "files" not in started.skills[0].model_dump()
    assert started.mcp_servers[0].model_dump()["command"] == ["math-server"]
    assert started.mcp_servers[0].status == "connected"
    assert json.loads((out.parent / "commission.json").read_bytes()) == supplied_json
    assert "skills" not in snapshots[-1].trajectory.agent.extra["avp"]
    assert "citations" in out.read_text()
    snapshots[-1].write(out)  # Repeated publication leaves the same start snapshot.
    assert not list(out.parent.rglob("*.tmp"))


def test_selected_inline_body_only_and_metadata_only_skills():
    commission = Commission.model_validate(
        {
            "avp_version": "0.1",
            "run_id": "r",
            "prompt": "task",
            "model": {"provider": "test", "id": "m"},
            "skills": [
                {
                    "name": "supplied",
                    "files": {"SKILL.md": "instructions", "support.txt": "support"},
                },
                {"name": "unused", "files": {"SKILL.md": "unused"}},
            ],
        }
    )
    assets: dict[str, bytes] = {}
    started = capture_start(
        {
            "prompt": "task",
            "model": {"provider": "test", "id": "m"},
            "skills": [
                {"name": "supplied", "description": "Selected"},
                {"name": "body", "description": "Body only", "files": {"instructions.md": "body"}},
                {"name": "opaque", "description": "No files exposed"},
            ],
        },
        commission,
        "r",
        assets,
    )
    assert started.skills and commission.skills
    assert started.skills[0].path == "skills/0-supplied"
    assert assets["skills/0-supplied/support.txt"] == b"support"
    assert assets["skills/1-body/instructions.md"] == b"body"
    assert started.skills[2].path is None
    assert len(started.skills) == 3


def test_unreadable_or_symlinked_skill_fails_capture(tmp_path):
    context = {
        "prompt": "task",
        "model": {"provider": "test", "id": "m"},
        "skills": [{"name": "s", "description": "s", "source": tmp_path.as_uri()}],
    }
    with pytest.raises(ValueError, match=r"SKILL\.md"):
        capture_start(context, None, "r", {})
    (tmp_path / "SKILL.md").write_text("skill")
    (tmp_path / "link").symlink_to(tmp_path / "SKILL.md")
    with pytest.raises(ValueError, match="regular files"):
        capture_start(context, None, "r", {})


def test_images_remain_atif_files_and_run_documents_cannot_be_overwritten(tmp_path):
    snapshots = []

    async def run():
        async def sink(snapshot):
            snapshots.append(snapshot)

        rec = Recorder(sink, run_id="r")
        await rec.start(RunContext(prompt="task", model=ModelRef(provider="test", id="m")))
        await rec.response(
            [
                ImageBlock(
                    type="image",
                    source=Source(
                        type="base64",
                        media_type="image/png",
                        data=base64.b64encode(b"image bytes").decode(),
                    ),
                )
            ]
        )
        await rec.stop("converged")

    asyncio.run(run())
    snapshot = snapshots[-1]
    snapshot.write(tmp_path / "trajectory.json")
    image = snapshot.trajectory.steps[-1].message[0].source.path
    assert (tmp_path / image).read_bytes() == b"image bytes"
    with pytest.raises(ValueError, match="conflicts"):
        snapshot.write(tmp_path / "agent-start.json")
    (tmp_path / "agent-start.json").write_text('{"run_id":"other"}')
    with pytest.raises(ValueError):
        snapshot.write(tmp_path / "trajectory.json")
    snapshot.assets["../escape"] = b"no"
    with pytest.raises(ValueError):
        snapshot.write(tmp_path / "other/trajectory.json")


def test_skill_paths_survive_moving_the_run_and_stdout_stays_trace_only(tmp_path, capsys):
    from avp.agent_cli.sink import trajectory_sink

    snapshots = []

    async def run():
        async def sink(snapshot):
            snapshots.append(snapshot)

        rec = Recorder(sink, run_id="r")
        await rec.start(
            RunContext.model_validate(
                {
                    "prompt": "task",
                    "model": {"provider": "test", "id": "m"},
                    "skills": [
                        {"name": "s", "description": "d", "files": {"instructions.md": "body"}}
                    ],
                }
            )
        )
        await rec.stop("converged", "done")
        await trajectory_sink(None)(snapshots[-1])

    asyncio.run(run())
    assert json.loads(capsys.readouterr().out)["session_id"] == "r"
    out = tmp_path / "run/trajectory.json"
    snapshots[-1].write(out)
    out.parent.rename(tmp_path / "moved")
    moved = tmp_path / "moved"
    started = AgentStart.model_validate_json((moved / "agent-start.json").read_bytes())
    assert started.skills and started.skills[0].path
    assert (moved / started.skills[0].path / "instructions.md").read_text() == "body"
    # Saved bytes cannot silently be changed by a later publication.
    (moved / started.skills[0].path / "instructions.md").write_text("changed")
    with pytest.raises(ValueError, match="different content"):
        snapshots[-1].write(moved / "trajectory.json")


def test_invalid_inline_paths_do_not_publish_partial_assets():
    assets = {}
    with pytest.raises(ValueError, match="relative"):
        capture_start(
            {
                "prompt": "task",
                "model": {"provider": "test", "id": "m"},
                "skills": [
                    {
                        "name": "s",
                        "description": "d",
                        "files": {
                            "instructions.md": "body",
                            "../escape": "bad",
                        },
                    }
                ],
            },
            None,
            "r",
            assets,
        )
    assert assets == {}

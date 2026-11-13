"""Four saved documents and complete, immutable start configuration."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import pytest

from avp.agent_start import AgentStart, capture_start
from avp.commission import Commission, ModelRef
from avp.descriptor import AgentDescriptor, Skill, Subagent
from avp.recorder import Recorder
from avp.reports import ImageBlock, RunContext, Source, TextBlock

CASES = Path(__file__).parents[2] / "testdata/agent-start.json"


@pytest.mark.parametrize("case", json.loads(CASES.read_text()), ids=lambda c: c["name"])
def test_shared_start_schema(case):
    if case["valid"]:
        AgentStart.model_validate(case["document"])
    else:
        with pytest.raises(ValueError):
            AgentStart.model_validate(case["document"])


def test_four_documents_keep_complete_start_without_extracted_skill_copies(tmp_path):
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
    }
    started = AgentStart.model_validate_json((out.parent / "agent-start.json").read_bytes())
    assert started.model.id == "resolved"
    assert started.system_prompt == ""
    assert started.output_schema == {"type": "object"}
    assert started.skills and started.skills[0].files
    assert started.subagents and started.subagents[0].skills
    assert started.mcp_servers
    assert started.skills[0].files["SKILL.md"] == original
    captured = started.skills[0].files["references/data.bin"]
    assert not isinstance(captured, str)
    assert base64.b64decode(captured.base64) == binary
    assert started.subagents[0].skills[0].files == started.skills[0].files
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
    )
    assert started.skills and commission.skills
    assert started.skills[0].files == commission.skills[0].files
    assert started.skills[1].files == {"instructions.md": "body"}
    assert started.skills[2].files is None
    assert len(started.skills) == 3


def test_unreadable_or_symlinked_skill_fails_capture(tmp_path):
    context = {
        "prompt": "task",
        "model": {"provider": "test", "id": "m"},
        "skills": [{"name": "s", "description": "s", "source": tmp_path.as_uri()}],
    }
    with pytest.raises(ValueError, match=r"SKILL\.md"):
        capture_start(context, None, "r")
    (tmp_path / "SKILL.md").write_text("skill")
    (tmp_path / "link").symlink_to(tmp_path / "SKILL.md")
    with pytest.raises(ValueError, match="regular files"):
        capture_start(context, None, "r")


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

"""Complete portable inputs, explicit outputs, and untrusted manifest boundaries."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from avp.artifacts import ArtifactFile, ArtifactManifest, read_artifacts, write_artifacts
from avp.commission import ModelRef
from avp.descriptor import AgentDescriptor, Skill
from avp.recorder import Recorder
from avp.reports import RunContext, TextBlock, ToolUseBlock

DATA = Path(__file__).parents[2] / "testdata/artifacts.json"


@pytest.mark.parametrize("case", json.loads(DATA.read_text()), ids=lambda c: c["name"])
def test_shared_manifest_cases(case):
    if case["valid"]:
        ArtifactManifest.model_validate(case["manifest"])
    else:
        with pytest.raises(ValueError):
            ArtifactManifest.model_validate(case["manifest"])


def test_capture_keeps_skill_bytes_and_config_out_of_trace(tmp_path):
    skill = tmp_path / "native-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: research\ndescription: Research.\n---\nUse references."
    )
    (skill / "references").mkdir()
    binary = b"\x00\xff\r\n"
    (skill / "references/data.bin").write_bytes(binary)
    out = tmp_path / "run/trajectory.json"
    snapshots = []
    arbitrary = {"extra": {"avp": {"annotations": {"unchanged": True}}}}

    async def run():
        async def sink(snapshot):
            snapshot.write(out)
            read_artifacts(out.parent, run_id="r")
            snapshots.append(snapshot)

        rec = Recorder(sink, run_id="r")
        await rec.begin(
            {
                "avp_version": "0.1",
                "run_id": "r",
                "prompt": "research",
                "model": {"provider": "test", "id": "m"},
            },
            AgentDescriptor(avp_version="0.1", agent_name="test", agent_version="1"),
        )
        await rec.start(
            RunContext(
                prompt="research",
                model=ModelRef(provider="test", id="m"),
                skills=[Skill(name="research", description="Research.", source=skill.as_uri())],
            )
        )
        (skill / "SKILL.md").write_text("changed during the run")
        await rec.artifact(
            "outputs/skills/research/SKILL.md", (skill / "SKILL.md").read_bytes(), role="output"
        )
        await rec.response(
            [
                ToolUseBlock(type="tool_use", id="c", name="echo", input=arbitrary),
                TextBlock(
                    type="text",
                    text="hi",
                    citations=[{"type": "url", "source_url": "https://example.com"}],
                ),
            ]
        )
        await rec.tool_returned("c", "ok")
        await rec.stop("converged", {"answer": 42})

    asyncio.run(run())
    manifest = read_artifacts(out.parent, run_id="r")
    assert (out.parent / "inputs/skills/research/references/data.bin").read_bytes() == binary
    assert (out.parent / "inputs/skills/research/SKILL.md").read_text().endswith("Use references.")
    effective = json.loads((out.parent / "inputs/effective-agent.json").read_text())
    assert effective["skills"][0]["source"] == "file:inputs/skills/research"
    assert "skills" not in snapshots[-1].trajectory.agent.extra["avp"]
    step = snapshots[-1].trajectory.steps[-1]
    assert step.tool_calls[0].arguments == arbitrary
    assert step.extra["avp"]["message_metadata"][0]["annotations"]["citations"] == [
        {"type": "url", "source_url": "https://example.com"}
    ]
    assert "citations" in out.read_text()
    assert not any(a.path.startswith("outputs/details/") for a in manifest.artifacts)
    assert "details_path" not in out.read_text()
    assert snapshots[-1].trajectory.extra["avp"]["output"] == {"answer": 42}
    assert not (out.parent / "outputs/result.json").exists()
    assert {a.role for a in manifest.artifacts} == {"input", "output"}
    assert not list(out.parent.rglob("*.tmp"))


def test_manifest_checks_hashes_missing_files_and_immutability(tmp_path):
    files = {"inputs/x.bin": ArtifactFile(b"hello", "input")}
    write_artifacts(tmp_path, "r", files)
    assert read_artifacts(tmp_path).artifacts[0].sha256 == hashlib.sha256(b"hello").hexdigest()
    with pytest.raises(ValueError, match="different run"):
        read_artifacts(tmp_path, run_id="other")
    with pytest.raises(ValueError, match="different content"):
        write_artifacts(tmp_path, "r", {"inputs/x.bin": ArtifactFile(b"changed", "input")})
    with pytest.raises(ValueError, match="different run"):
        write_artifacts(tmp_path, "other", files)
    with pytest.raises(ValueError, match="immutable"):
        write_artifacts(tmp_path, "r", {})
    with pytest.raises(ValueError, match="immutable"):
        write_artifacts(tmp_path, "r", {"inputs/x.bin": ArtifactFile(b"hello", "output")})
    (tmp_path / "inputs/x.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_artifacts(tmp_path)
    (tmp_path / "inputs/x.bin").unlink()
    with pytest.raises(FileNotFoundError):
        read_artifacts(tmp_path)


def test_symlink_cannot_escape_artifact_directory(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "escape").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        write_artifacts(out, "r", {"escape/outside": ArtifactFile(b"no", "output")})
    assert not (tmp_path / "outside").exists()

"""Validate native adapter test outputs as ATIF. Uses no provider credentials."""

import json
import math
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from avp.trajectory import parse_trajectory_event
from avp.utils.atif import to_atif

ROOT = Path(__file__).resolve().parent.parent
TARGETS = (
    "codex-check",
    "pydantic-ai-check",
    "claude-check",
    "openai-agents-check",
    "deep-agents-check",
    "pi-check",
    "gemini-cli-check",
    "opencode-check",
)
AGENTS = {
    "avp-codex",
    "avp-pydantic-ai",
    "avp-claude-agent-sdk",
    "avp-openai-agents",
    "avp-deep-agents",
    "avp-pi",
    "avp-gemini-cli",
    "avp-opencode",
}
SCHEMA = Draft202012Validator(json.loads((ROOT / "avp-sdk/testdata/atif/schema.json").read_text()))


def documents(root):
    yield root
    for child in root.get("subagent_trajectories", []):
        yield from documents(child)


def check(source: Path) -> str:
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    events = [parse_trajectory_event(row) for row in rows]
    assert events and all(event is not None for event in events), source
    bundle = to_atif(events)
    root = bundle.trajectory
    SCHEMA.validate(root)
    run_id = rows[0]["run_id"]
    by_scope = {
        None if doc is root else doc["trajectory_id"].removeprefix(f"{run_id}/subagent/"): doc
        for doc in documents(root)
    }
    observations = {}
    for scope, doc in by_scope.items():
        assert [s["step_id"] for s in doc["steps"]] == list(range(1, len(doc["steps"]) + 1))
        children = {c["trajectory_id"] for c in doc.get("subagent_trajectories", [])}
        assert len(children) == len(doc.get("subagent_trajectories", []))
        for step in doc["steps"]:
            call_ids = {c["tool_call_id"] for c in step.get("tool_calls", [])}
            for result in step.get("observation", {}).get("results", []):
                if "source_call_id" in result:
                    assert result["source_call_id"] in call_ids
                    observations[(scope, result["source_call_id"])] = result
                for reference in result.get("subagent_trajectory_ref", []):
                    assert reference["trajectory_id"] in children
            contents = [
                step["message"],
                *[r.get("content") for r in step.get("observation", {}).get("results", [])],
            ]
            for content in contents:
                if isinstance(content, list):
                    for part in content:
                        if part["type"] == "image":
                            assert part["source"]["path"] in bundle.assets
        responses = [
            row["data"]
            for row in rows
            if row["type"] == "assistant_message"
            and row["data"].get("subagent_invocation_id") == scope
        ]
        steps = [s for s in doc["steps"] if s["source"] == "agent"]
        assert len(steps) == len(responses)
        for response, step in zip(responses, steps, strict=True):
            assert step["llm_call_count"] == 1
            assert step["metrics"]["prompt_tokens"] == response["usage"]["input_tokens"]
            assert step["metrics"]["completion_tokens"] == response["usage"]["output_tokens"]
            if response["usage"]["cost_source"] == "unknown":
                assert "cost_usd" not in step["metrics"]
            else:
                assert math.isclose(step["metrics"]["cost_usd"], response["usage"]["cost_usd"])
            assert step["extra"]["avp"]["duration_ms"] == response["duration_ms"]
    for row in rows:
        data = row["data"]
        if row["type"] == "tool_returned":
            result = observations[(data.get("subagent_invocation_id"), data["tool_call_id"])]
            assert result["extra"]["avp"]["is_error"] == data["tool_result"].get("is_error", False)
            assert result["extra"]["avp"].get("structured_content") == data["tool_result"].get(
                "structured_content"
            )
        elif row["type"] == "agent_stopped":
            assert root["extra"]["avp"]["complete"]
            assert root["extra"]["avp"]["stop_reason"] == data["reason"]
            assert root["extra"]["avp"].get("output") == data.get("output")
    assert not {"events", "event_metadata", "event_defaults"} & root["extra"]["avp"].keys()
    return root["agent"]["name"]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="avp-atif-adapters-") as directory:
        env = {
            **os.environ,
            "AVP_ATIF_CAPTURE": directory,
            "PYTHONPATH": os.pathsep.join(
                filter(None, [str(ROOT / "testing/atif"), os.environ.get("PYTHONPATH")])
            ),
            "PYTEST_PLUGINS": ",".join(
                filter(None, [os.environ.get("PYTEST_PLUGINS"), "atif_capture"])
            ),
        }
        env.pop("VIRTUAL_ENV", None)  # Each adapter owns its environment.
        subprocess.run(["make", *TARGETS], cwd=ROOT, env=env, check=True)
        counts = Counter()
        for source in sorted(Path(directory).glob("*.ndjson")):
            try:
                counts[check(source)] += 1
            except Exception as error:
                raise AssertionError(
                    f"ATIF adapter check failed for {source.name}: {error}"
                ) from error
        assert counts.keys() == AGENTS, f"Missing adapter outputs: {AGENTS - counts.keys()}"
        for name, count in sorted(counts.items()):
            print(f"ATIF {name}: {count} native test trajectories passed")


if __name__ == "__main__":
    main()

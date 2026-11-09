"""Validate native adapter test outputs as ATIF. Uses no provider credentials."""

import json
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from avp.trajectory import parse_trajectory

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
    root = parse_trajectory(source.read_text()).to_json_dict()
    SCHEMA.validate(root)
    for doc in documents(root):
        assert [s["step_id"] for s in doc["steps"]] == list(range(1, len(doc["steps"]) + 1))
        for step in doc["steps"]:
            if step["source"] == "agent":
                assert step["llm_call_count"] == 1
            call_ids = {c["tool_call_id"] for c in step.get("tool_calls", [])}
            for result in step.get("observation", {}).get("results", []):
                if "source_call_id" in result:
                    assert result["source_call_id"] in call_ids
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
        for source in sorted(Path(directory).glob("*.json")):
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

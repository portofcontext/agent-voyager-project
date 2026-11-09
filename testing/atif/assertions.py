"""Small ATIF queries for runtime integration tests. No AVP event projection."""

from datetime import datetime
from pathlib import Path

from avp.trajectory import parse_trajectory


def load(path: Path) -> dict:
    return parse_trajectory(path.read_text()).to_json_dict()


def meta(value: dict) -> dict:
    return value.get("extra", {}).get("avp", {})


def documents(root: dict):
    yield root
    for child in root.get("subagent_trajectories", []):
        yield from documents(child)


def responses(root: dict) -> list[dict]:
    return sorted(
        [s for d in documents(root) for s in d["steps"] if s["source"] == "agent"],
        key=lambda s: datetime.fromisoformat(s["timestamp"]),
    )


def calls(root: dict) -> list[dict]:
    return [c for s in responses(root) for c in s.get("tool_calls", [])]


def results(root: dict) -> list[dict]:
    return [
        r
        for d in documents(root)
        for s in d["steps"]
        for r in s.get("observation", {}).get("results", [])
        if "content" in r
    ]


def children(root: dict) -> list[dict]:
    return list(documents(root))[1:]


def errors(root: dict) -> list[dict]:
    return [s for d in documents(root) for s in d["steps"] if meta(s).get("error_code")]

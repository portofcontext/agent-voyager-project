"""Capture explicitly supplied inputs without crawling an agent's workspace."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from avp.artifacts import ArtifactFile, Role


class ArtifactCollection:
    def __init__(self) -> None:
        self.files: dict[str, ArtifactFile] = {}
        self.commission: dict[str, Any] = {}

    def add(self, path: str, content: bytes, role: Role) -> None:
        file = ArtifactFile(content, role)
        file.entry(path)
        if path in {"artifacts.json", "trajectory.json"}:
            raise ValueError(f"reserved artifact path: {path}")
        if path in self.files and self.files[path] != file:
            raise ValueError(f"artifact is immutable; use a new path: {path}")
        self.files[path] = file

    def json(self, path: str, data: Any, role: Role) -> None:
        self.add(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode(), role)

    def begin(self, commission: dict[str, Any] | None, descriptor: dict[str, Any]) -> None:
        self.commission = commission or {}
        if commission is not None:
            self.json("inputs/commission.json", commission, "input")
            for skill in commission.get("skills", []):
                for name, text in skill["files"].items():
                    self.add(
                        f"inputs/skills/{quote(skill['name'], safe='')}/{name}",
                        text.encode(),
                        "input",
                    )
        self.json("inputs/descriptor.json", descriptor, "input")

    def effective(self, context: dict[str, Any], meta: dict[str, Any] | None) -> None:
        context = deepcopy(context)

        def skills(items: list[dict[str, Any]], prefix: str) -> None:
            for skill in items:
                destination = f"{prefix}/{quote(skill['name'], safe='')}"
                source = skill.get("source")
                if source:
                    uri = urlsplit(source)
                    if uri.scheme != "file" or uri.netloc not in {"", "localhost"}:
                        raise ValueError(f"skill source must be a local file URI: {source}")
                    root = Path(unquote(uri.path)).resolve(strict=True)
                    if not (root / "SKILL.md").is_file():
                        raise ValueError(f"skill source has no SKILL.md: {source}")
                    for file in sorted(root.rglob("*")):
                        if file.is_symlink():
                            raise ValueError(f"skill capture requires regular files: {file}")
                        if file.is_file():
                            self.add(
                                f"{destination}/{file.relative_to(root).as_posix()}",
                                file.read_bytes(),
                                "input",
                            )
                elif f"inputs/skills/{quote(skill['name'], safe='')}/SKILL.md" in self.files:
                    destination = f"inputs/skills/{quote(skill['name'], safe='')}"
                else:
                    continue
                skill["source"] = f"file:{destination}"

        skills(context.get("skills", []), "inputs/skills")
        for child in context.get("subagents", []):
            skills(
                child.get("skills", []), f"inputs/subagents/{quote(child['name'], safe='')}/skills"
            )
        if "output_schema" in self.commission:
            context["output_schema"] = self.commission["output_schema"]
        if meta:
            context["annotations"] = meta
        self.json("inputs/effective-agent.json", context, "input")

    def compact(self, value: Any, path: str = "root") -> None:
        """Move bulky annotations into files while keeping a direct trace reference."""
        if isinstance(value, list):
            for index, item in enumerate(value):
                self.compact(item, f"{path}/{index}")
        elif isinstance(value, dict):
            metadata = value.get("extra", {}).get("avp", {})
            details = {
                key: metadata.pop(key)
                for key in (
                    "annotations",
                    "message_metadata",
                    "reasoning_metadata",
                    "provider_metadata",
                    "content_metadata",
                    "base_url",
                )
                if key in metadata
            }
            if details:
                name = f"outputs/details/{path}.json"
                self.json(name, details, "output")
                metadata["details_path"] = name
            for key, item in value.items():
                if key in {
                    "agent",
                    "steps",
                    "tool_calls",
                    "observation",
                    "results",
                    "metrics",
                    "final_metrics",
                    "subagent_trajectories",
                }:
                    self.compact(item, f"{path}/{key}")

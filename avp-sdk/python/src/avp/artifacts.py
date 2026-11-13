"""Small run manifests and immutable, byte-preserving artifact publication."""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from avp._base import WireModel

Role = Literal["input", "output"]
PATH_PATTERN = r"^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))(?!.*//)(?!.*[\\:\x00-\x1f])[^/]+(?:/[^/]+)*$"


class Artifact(WireModel):
    path: str = Field(pattern=re.compile(PATH_PATTERN))
    role: Role
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ArtifactManifest(WireModel):
    avp_version: Literal["0.1"]
    run_id: str
    artifacts: list[Artifact]

    @model_validator(mode="after")
    def _unique_paths(self) -> Self:
        if len({a.path for a in self.artifacts}) != len(self.artifacts):
            raise ValueError("artifact paths must be unique")
        return self


@dataclass(frozen=True)
class ArtifactFile:
    content: bytes
    role: Role

    def entry(self, path: str) -> Artifact:
        return Artifact(path=path, role=self.role, sha256=hashlib.sha256(self.content).hexdigest())


def artifact_path(directory: Path, name: str) -> Path:
    """Resolve a validated relative path without following links outside the run."""
    Artifact(path=name, role="input", sha256="0" * 64)
    target = directory / name
    if not target.resolve().is_relative_to(directory.resolve()):
        raise ValueError("artifact path escapes the run directory")
    return target


def atomic_write(path: Path, content: bytes) -> None:
    """Replace a file with ordinary creation permissions, filtered by umask."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    file = temporary.open("xb")
    try:
        with file:
            file.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_artifacts(directory: Path, run_id: str, files: dict[str, ArtifactFile]) -> None:
    entries = [file.entry(name) for name, file in sorted(files.items())]
    manifest_path = directory / "artifacts.json"
    if manifest_path.exists():
        previous = ArtifactManifest.model_validate_json(manifest_path.read_bytes())
        if previous.run_id != run_id:
            raise ValueError("artifact manifest belongs to a different run")
        current = {entry.path: entry for entry in entries}
        if any(current.get(entry.path) != entry for entry in previous.artifacts):
            raise ValueError(
                "published artifacts are immutable; use a new path for different content"
            )
    for entry in entries:
        if entry.path == "artifacts.json":
            raise ValueError("artifacts.json is reserved for the manifest")
        target = artifact_path(directory, entry.path)
        content = files[entry.path].content
        if target.exists():
            if target.read_bytes() != content:
                raise ValueError(f"artifact already exists with different content: {entry.path}")
        else:
            atomic_write(target, content)
    manifest = ArtifactManifest(avp_version="0.1", run_id=run_id, artifacts=entries)
    atomic_write(directory / "artifacts.json", (manifest.model_dump_json(indent=2) + "\n").encode())


def read_artifacts(directory: Path, *, run_id: str | None = None) -> ArtifactManifest:
    """Read a manifest and verify every listed file before using its contents."""
    manifest = ArtifactManifest.model_validate_json((directory / "artifacts.json").read_bytes())
    if run_id is not None and manifest.run_id != run_id:
        raise ValueError("artifact manifest belongs to a different run")
    for entry in manifest.artifacts:
        content = artifact_path(directory, entry.path).read_bytes()
        if hashlib.sha256(content).hexdigest() != entry.sha256:
            raise ValueError(f"artifact hash mismatch: {entry.path}")
    return manifest

"""Publish run documents and ATIF-referenced files."""

import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel


def local_path(directory: Path, name: str) -> Path:
    if (
        not name
        or any(c in name for c in "\\:\x00")
        or any(p in {"", ".", ".."} for p in name.split("/"))
    ):
        raise ValueError("file path must be relative to the run directory")
    target = directory / name
    if not target.resolve().is_relative_to(directory.resolve()):
        raise ValueError("file path escapes the run directory")
    return target


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("xb") as file:
            file.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_document(directory: Path, name: str, document: BaseModel) -> None:
    data = document.model_dump(mode="json", exclude_none=True)
    path = local_path(directory, name)
    if path.exists():
        existing = type(document).model_validate_json(path.read_bytes())
        if existing.model_dump(mode="json", exclude_none=True) != data:
            raise ValueError(f"run document already exists with different content: {name}")
    else:
        atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())

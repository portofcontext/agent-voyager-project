"""Schema-validate every conformance case file against test-case.schema.json.

The test-case schema `$ref`s into the v0.1 AVP schema bundle, so we register
those resources too. Returns a list of (path, errors) for any case that
failed; empty list means everything validated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


@dataclass
class ValidationFailure:
    path: Path
    errors: list[str]


def _load(p: Path) -> dict:
    with p.open() as f:
        return json.load(f)


def _build_registry(spec_dir: Path, test_case_schema_path: Path) -> Registry:
    """Register the v0.1 AVP schemas plus the test-case schema by their $id URIs
    so jsonschema can resolve $refs across the bundle."""
    registry: Registry = Registry()
    schema_files = [
        spec_dir / "avp.schema.json",
        spec_dir / "commission.schema.json",
        spec_dir / "event.schema.json",
        test_case_schema_path,
    ]
    for sf in schema_files:
        doc = _load(sf)
        registry = registry.with_resource(uri=doc["$id"], resource=Resource.from_contents(doc))
    return registry


def validate_suite(
    *,
    suite_dir: Path,
    spec_dir: Path,
    test_case_schema_path: Path,
) -> tuple[list[Path], list[ValidationFailure]]:
    """Validate every *.json under suite_dir against the test-case schema.

    Returns (all_cases, failures). all_cases is the full list found;
    failures is empty iff every case validated.
    """
    test_case_schema = _load(test_case_schema_path)
    Draft202012Validator.check_schema(test_case_schema)

    registry = _build_registry(spec_dir, test_case_schema_path)
    validator = Draft202012Validator(test_case_schema, registry=registry)

    cases = sorted(suite_dir.rglob("*.json"))
    failures: list[ValidationFailure] = []

    for path in cases:
        errs = _validate_one(path, validator)
        if errs:
            failures.append(ValidationFailure(path=path, errors=errs))

    return cases, failures


def _validate_one(path: Path, validator: Draft202012Validator) -> list[str]:
    try:
        doc = _load(path)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]
    msgs: list[str] = []
    for err in validator.iter_errors(doc):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        msgs.append(f"{loc}: {err.message[:300]}")
    if doc.get("id") and path.stem != doc["id"]:
        msgs.append(f"id mismatch: file stem '{path.stem}' != case id '{doc['id']}'")
    return msgs

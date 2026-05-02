#!/usr/bin/env python3
"""
Validate every test case under cases/**/*.json against schema/test-case.schema.json.

The test-case schema $refs into the v0.1 AEP bundle (config.schema.json,
supervisor-message.schema.json), so this script registers those too.

Run:  python3 validate.py
Exit: 0 if all cases parse and validate; non-zero on any failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:
    sys.stderr.write("Missing dependencies. Install with: pip install jsonschema referencing\n")
    sys.exit(2)


HERE = Path(__file__).resolve().parent
SPEC_DIR = HERE.parent.parent / "spec" / "v0.1"


def load(p: Path) -> dict:
    with p.open() as f:
        return json.load(f)


def build_registry() -> Registry:
    """Register all v0.1 schemas plus the test-case schema by their $id URIs."""
    registry = Registry()
    schema_files = [
        SPEC_DIR / "aep.schema.json",
        SPEC_DIR / "config.schema.json",
        SPEC_DIR / "event.schema.json",
        SPEC_DIR / "supervisor-message.schema.json",
        HERE / "schema" / "test-case.schema.json",
    ]
    for sf in schema_files:
        doc = load(sf)
        registry = registry.with_resource(uri=doc["$id"], resource=Resource.from_contents(doc))
    return registry


def validate_one(path: Path, validator: Draft202012Validator) -> list[str]:
    try:
        doc = load(path)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]
    errors = list(validator.iter_errors(doc))
    msgs = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        msgs.append(f"{loc}: {err.message[:300]}")
    if doc.get("id") and path.stem != doc["id"]:
        msgs.append(f"id mismatch: file stem '{path.stem}' != case id '{doc['id']}'")
    return msgs


def main() -> int:
    test_case_schema = load(HERE / "schema" / "test-case.schema.json")
    Draft202012Validator.check_schema(test_case_schema)

    registry = build_registry()
    validator = Draft202012Validator(test_case_schema, registry=registry)

    cases_dir = HERE / "cases"
    cases = sorted(cases_dir.rglob("*.json"))
    if not cases:
        print(f"No cases found under {cases_dir}", file=sys.stderr)
        return 1

    fails = 0
    for path in cases:
        rel = path.relative_to(HERE)
        errs = validate_one(path, validator)
        if errs:
            fails += 1
            print(f"FAIL  {rel}")
            for e in errs:
                print(f"      {e}")
        else:
            print(f"PASS  {rel}")

    print()
    print(f"{len(cases) - fails} / {len(cases)} cases valid")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

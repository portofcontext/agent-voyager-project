"""Verify every AEP event type declared in the schema has at least one
conformance case that asserts on it.

The deterministic floor of the seams principle (CLAUDE.md): adds-without-tests
stop being silent. Hooks into CI so a new event type without a corresponding
conformance case fails the build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Event types declared in the schema but NOT emitted by any v0.1 runner.
# Conformance cases here would have nothing to assert against. Each entry
# carries a reason; remove from this set when a runner starts emitting the
# event AND a conformance case is added.
DEFERRED_COVERAGE: dict[str, str] = {
    "skill_executed": (
        "schema-only: no v0.1 runner emits skill_executed yet. The reference "
        "runner emits skill_loaded; skill activation is runner-specific and "
        "not exercised by ScriptedModel-based conformance harness."
    ),
}


@dataclass
class CoverageReport:
    declared: set[str]
    covered: set[str]
    deferred: set[str]
    uncovered: set[str]  # genuine gaps — not in deferred

    @property
    def ok(self) -> bool:
        return not self.uncovered


def event_types_from_schema(schema_path: Path) -> set[str]:
    """Collect every event-type literal in the schema's $defs.

    Each event def has properties.type.const = '<event_type>'. We walk $defs
    and collect those, filtering by the def name suffix 'Event' so non-event
    consts ('runner', 'supervisor', schema_version values) don't bleed in.
    """
    bundle = json.loads(schema_path.read_text())
    out: set[str] = set()
    for name, definition in (bundle.get("$defs") or {}).items():
        if not name.endswith("Event"):
            continue
        type_prop = (definition.get("properties") or {}).get("type") or {}
        const = type_prop.get("const")
        if isinstance(const, str):
            out.add(const)
    return out


def event_types_in_case(case: dict[str, Any]) -> set[str]:
    """Find every event type referenced in a case's expectations."""
    found: set[str] = set()
    expectations = case.get("expectations") or {}
    for matcher_block in (
        expectations.get("events") or [],
        expectations.get("forbidden_events") or [],
    ):
        for matcher in matcher_block:
            t = (matcher.get("match") or {}).get("type")
            if isinstance(t, str):
                found.add(t)
    return found


def check_coverage(*, schema_path: Path, cases_dir: Path) -> CoverageReport:
    declared = event_types_from_schema(schema_path)
    covered: set[str] = set()
    for path in sorted(cases_dir.rglob("*.json")):
        try:
            case = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        covered |= event_types_in_case(case)

    deferred = declared & set(DEFERRED_COVERAGE)
    uncovered = declared - covered - set(DEFERRED_COVERAGE)
    return CoverageReport(
        declared=declared,
        covered=covered,
        deferred=deferred,
        uncovered=uncovered,
    )

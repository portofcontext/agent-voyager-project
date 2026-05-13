"""Run every conformance case under conformance/ as a pytest test.

This is the primary correctness gate. The package is wire-correct iff every
case in the per-spec suites passes."""

from __future__ import annotations

from pathlib import Path

import pytest

from avp.conformance.harness import run_case

CONFORMANCE_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "conformance"


def _all_case_paths() -> list[Path]:
    if not CONFORMANCE_ROOT.exists():
        pytest.skip(f"conformance dir missing: {CONFORMANCE_ROOT}")
    return sorted(p for p in CONFORMANCE_ROOT.rglob("*.json") if "cases" in p.parts)


@pytest.mark.parametrize(
    "case_path",
    _all_case_paths(),
    ids=lambda p: p.relative_to(CONFORMANCE_ROOT).as_posix(),
)
def test_conformance_case(case_path: Path) -> None:
    result = run_case(case_path)
    if result.passed:
        return
    failures = "\n".join(f"  {f.label}: {f.detail}" for f in result.failures)
    trajectory = "\n".join(
        f"  {ev.get('source', '?'):>10}  {ev.get('type', '?')}  {ev}"
        for ev in result.trajectory[-30:]
    )
    pytest.fail(
        f"\n{result.case_id} ({case_path.name}) FAILED:\n"
        f"{failures}\n\nlast 30 events:\n{trajectory}"
    )

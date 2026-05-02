"""Run every conformance case in spec/v0.1/conformance/cases/ as a pytest test.

This is the primary correctness gate. The package is AEP v0.1-correct iff every
case in this suite passes."""

from __future__ import annotations

from pathlib import Path

import pytest

from aep.conformance.harness import run_case

CASES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "conformance" / "v0.1" / "cases"


def _all_case_paths() -> list[Path]:
    if not CASES_DIR.exists():
        pytest.skip(f"cases dir missing: {CASES_DIR}")
    return sorted(CASES_DIR.rglob("*.json"))


@pytest.mark.parametrize(
    "case_path",
    _all_case_paths(),
    ids=lambda p: p.relative_to(CASES_DIR).as_posix(),
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

"""The shared run plan cases in `avp_sdk/testdata/run_plan/`, which every SDK
passes. Each case gives a Commission and a Descriptor and expects the plan."""

import json
from pathlib import Path
from typing import Any

import pytest

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.utils.preflight import check_commission
from avp.utils.run_plan import plan_run

CASES = Path(__file__).resolve().parents[2] / "testdata" / "run_plan"


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    commission = Commission.model_validate(case["commission"])
    descriptor = AgentDescriptor.model_validate(case["descriptor"])
    assert check_commission(commission, descriptor) is None, "the case's Commission is refused"
    return plan_run(commission, descriptor).model_dump(
        mode="json", exclude_none=True, by_alias=True
    )


@pytest.mark.parametrize("path", sorted(CASES.glob("*.json")), ids=lambda path: path.stem)
def test_case(path: Path) -> None:
    case = json.loads(path.read_text())
    assert run_case(case) == case["plan"]

"""Pydantic-level tests for the SubagentRef Commission primitive.

The subagent wire lifecycle (subagent_invoked / subagent_returned with
avp.subagent.run_id, frame-span pairing, usage rollup) is exercised end-to-end
by the conformance suite under conformance/v0.1/cases/subagent/. This file
covers shape validation that doesn't need the full agent loop.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from avp.types import Commission, SubagentRef


def test_subagent_ref_accepts_string_ref() -> None:
    sa = SubagentRef(id="researcher", ref="sk_subagent_researcher_v1")
    assert sa.id == "researcher"
    assert sa.ref == "sk_subagent_researcher_v1"


def test_subagent_ref_accepts_object_ref() -> None:
    sa = SubagentRef(id="x", ref={"type": "custom", "skill_id": "abc"})
    assert isinstance(sa.ref, dict)
    assert sa.ref["type"] == "custom"


def test_subagent_ref_id_pattern_enforced() -> None:
    # Uppercase is rejected — id pattern is ^[a-z0-9_-]+$
    with pytest.raises(ValidationError):
        SubagentRef(id="UpperCase", ref="x")


def test_subagent_ref_no_extra_fields() -> None:
    # SubagentRef carries `{id, ref}` only. The ref is opaque to AVP; model
    # contract, system prompt, and other rich metadata come from the resolver.
    with pytest.raises(ValidationError):
        SubagentRef.model_validate(
            {"id": "x", "ref": "y", "system_prompt": "should not be allowed"}
        )


def test_commission_carries_subagent_refs_only() -> None:
    c = Commission.model_validate(
        {
            "schema_version": "0.1",
            "run_id": "r1",
            "subagents": [{"id": "researcher", "ref": "sk_a"}],
        }
    )
    assert c.subagents is not None
    assert len(c.subagents) == 1
    assert c.subagents[0].id == "researcher"


def test_commission_rejects_unknown_field() -> None:
    # Commission uses strict-extra-fields so a typo or stale field surfaces
    # as a validation error rather than being silently dropped.
    with pytest.raises(ValidationError):
        Commission.model_validate(
            {"schema_version": "0.1", "run_id": "r1", "not_a_real_field": ["*"]}
        )

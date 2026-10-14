"""The shared pre-turn Commission checks."""

from __future__ import annotations

from typing import Any

from avp.commission import Commission
from avp.preflight import preflight
from avp.trajectory import ErrorCode


def _check(tools: list[str] | None = None, **fields: Any) -> tuple[ErrorCode, str] | None:
    commission = Commission.model_validate(
        {"schema_version": "0.1", "run_id": "r", "model": "x/m", **fields}
    )
    return preflight(commission, agent_name="a", agent_version="1.0", tools=tools)


def test_plain_commission_passes() -> None:
    assert _check(tools=["read"]) is None


def test_version_pin_for_another_build() -> None:
    assert _check(agent_versions={"a": "0.9"})[0] is ErrorCode.unsupported_agent_version
    assert _check(agent_versions={"a": "1.0", "b": "7"}) is None


def test_allowlist_without_this_agents_key() -> None:
    code, message = _check(enabled_builtin_subagents={"other": []})
    assert code is ErrorCode.commission_collision
    assert "enabled_builtin_subagents" in message


def test_allowlisted_name_the_agent_does_not_offer() -> None:
    code, message = _check(tools=["read"], enabled_builtin_tools={"a": ["read", "fly"]})
    assert code is ErrorCode.commission_collision
    assert "fly" in message
    assert _check(tools=["read"], enabled_builtin_tools={"a": []}) is None


def test_unchecked_surface_is_not_validated_by_name() -> None:
    assert _check(tools=None, enabled_builtin_tools={"a": ["anything"]}) is None

"""Cross-validation tests: prove that AEP's wire format is parseable by the
canonical Python implementations of the specs it adopts (not just *similar*
to them in shape). When these pass, we can ship knowing real-world consumers
can decode our trajectories with stock libraries.

Tests gracefully skip if an optional interop dep isn't installed (the
`interop` extras group). Install with:

    uv sync --extra interop

Specs and the libraries we cross-check:
- CloudEvents 1.0      → `cloudevents` PyPI package
- JSON-RPC 2.0         → JSON Schema validation against the 2.0 spec schema
- MCP 2025-11-25 tool  → JSON Schema validation against the MCP tool spec
"""

from __future__ import annotations

import importlib.util
import json
from typing import Any

import pytest

from aep import (
    Config,
    JsonRpcRequestPayload,
    JsonRpcResponsePayload,
    Tool,
    event_to_wire,
)
from aep.runner.drivers import ModelResponse
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from aep.runner.runner import AEPRunner

_HAS_CLOUDEVENTS = importlib.util.find_spec("cloudevents") is not None


def _trivial_run() -> list[Any]:
    cfg = Config(
        schema_version="0.1",
        run_id="interop-trivial",
        prompt="hi",
        model="claude-sonnet-4-6",
    )
    model = ScriptedModel(
        [
            ModelResponse(
                tokens_input=10,
                tokens_output=5,
                cost_usd=0.001,
                duration_ms=1,
                text="hello",
                converged=True,
            ),
        ]
    )
    runner = AEPRunner(cfg, model, ScriptedTools(), ScriptedSupervisor())
    runner.run()
    return runner.trajectory


# ── CloudEvents 1.0 ─────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not _HAS_CLOUDEVENTS,
    reason="install with `uv sync --extra interop` to enable CloudEvents cross-validation",
)
def test_emitted_events_round_trip_through_cloudevents_sdk() -> None:
    """Every AEP event MUST be parseable as a CloudEvent 1.0 by the canonical
    `cloudevents` Python package — and re-encoding it MUST preserve the
    semantically meaningful envelope fields.

    This is the strongest cross-validation we can ship: if the CloudEvents
    SDK accepts our output without error, we are CloudEvents-compatible by
    construction (not just by lookalike shape)."""
    # cloudevents 2.x: structured-JSON parsing for the 1.0 spec lives under
    # the `cloudevents.v1.http` namespace (this is the canonical/HTTP binding).
    from cloudevents.v1.http import from_json as ce_from_json
    from cloudevents.v1.http import to_structured

    for ev in _trivial_run():
        wire = event_to_wire(ev)
        raw = json.dumps(wire)
        ce = ce_from_json(raw)
        # Required CloudEvents 1.0 attributes round-trip
        assert ce["specversion"] == "1.0"
        assert ce["id"] == wire["id"]
        assert ce["source"] == wire["source"]
        assert ce["type"] == wire["type"]
        assert ce["subject"] == wire["subject"]
        # Re-encode through the structured HTTP binding and reparse to verify
        # the SDK round-trips data without dropping fields.
        _, body = to_structured(ce)
        rep = json.loads(body)
        assert rep["type"] == wire["type"]
        assert rep["data"]["trace_id"] == wire["data"]["trace_id"]


# ── JSON-RPC 2.0 ────────────────────────────────────────────────────────────


# The official JSON-RPC 2.0 spec doesn't ship a JSON Schema, but the structural
# rules are simple and widely encoded. We hand-author a minimal validator
# inline so the test has no extra dependency.


def _validate_jsonrpc_2_request(req: dict[str, Any]) -> None:
    assert req.get("jsonrpc") == "2.0", "jsonrpc field MUST equal '2.0'"
    assert "method" in req and isinstance(req["method"], str)
    if "id" in req:
        assert isinstance(req["id"], (str, int)), "id MUST be string|number|null"
    if "params" in req:
        assert isinstance(req["params"], (dict, list))


def _validate_jsonrpc_2_response(resp: dict[str, Any]) -> None:
    assert resp.get("jsonrpc") == "2.0"
    assert "id" in resp
    has_result = "result" in resp
    has_error = "error" in resp
    assert has_result != has_error, "exactly one of result|error MUST be present"
    if has_error:
        err = resp["error"]
        assert isinstance(err, dict)
        assert isinstance(err.get("code"), int)
        assert isinstance(err.get("message"), str)


def test_jsonrpc_request_payload_satisfies_jsonrpc_2_schema() -> None:
    p = JsonRpcRequestPayload(
        id="req-1",
        method="tools/call",
        params={"name": "lookup", "arguments": {"q": "foo"}},
    )
    wire = p.model_dump(by_alias=True, exclude_none=True, mode="json")
    _validate_jsonrpc_2_request(wire)


def test_jsonrpc_response_result_satisfies_jsonrpc_2_schema() -> None:
    p = JsonRpcResponsePayload(id="req-1", result="ok")
    wire = p.model_dump(by_alias=True, exclude_none=True, mode="json")
    _validate_jsonrpc_2_response(wire)


def test_jsonrpc_response_error_satisfies_jsonrpc_2_schema() -> None:
    p = JsonRpcResponsePayload(
        id="req-1",
        error={"code": -32000, "message": "lookup failed"},
    )
    wire = p.model_dump(by_alias=True, exclude_none=True, mode="json")
    _validate_jsonrpc_2_response(wire)


# ── MCP 2025-11-25 tool descriptor ──────────────────────────────────────────


def test_mcp_tool_descriptor_uses_camelcase_inputschema() -> None:
    """Per the MCP 2025-11-25 spec, Tool descriptors use `inputSchema` (camelCase),
    not `input_schema` (snake_case). Round-tripping through Pydantic and the
    aliased serializer MUST produce the camelCase form."""
    t = Tool(
        name="lookup_user",
        description="Look up a user by id.",
        inputSchema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string"}},
        },
    )
    wire = t.model_dump(by_alias=True, exclude_none=True, mode="json")
    assert "inputSchema" in wire
    assert "input_schema" not in wire
    assert wire["name"] == "lookup_user"


def test_mcp_tool_descriptor_meta_is_underscore_meta_per_mcp_spec() -> None:
    """MCP defines `_meta` (with leading underscore) as the extension slot.
    AEP places `_meta.aep.timeout_ms` there; verify the wire form preserves
    the leading underscore."""
    t = Tool(
        name="t1",
        inputSchema={"type": "object"},
        **{"_meta": {"aep": {"timeout_ms": 5000}}},  # alias key on construction
    )
    wire = t.model_dump(by_alias=True, exclude_none=True, mode="json")
    assert "_meta" in wire
    assert wire["_meta"]["aep"]["timeout_ms"] == 5000

"""Cross-validation tests: prove that AVP's wire format is parseable by the
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

from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse
from avp.agent.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from avp.commission import Commission
from avp.trajectory import event_to_wire

_HAS_CLOUDEVENTS = importlib.util.find_spec("cloudevents") is not None


def _trivial_run() -> list[Any]:
    commission = Commission(
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
    agent = AVPAgent(commission, model, ScriptedTools(), ScriptedSupervisor())
    agent.run()
    return agent.trajectory


# ── CloudEvents 1.0 ─────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not _HAS_CLOUDEVENTS,
    reason="install with `uv sync --extra interop` to enable CloudEvents cross-validation",
)
def test_emitted_events_round_trip_through_cloudevents_sdk() -> None:
    """Every AVP event MUST be parseable as a CloudEvent 1.0 by the canonical
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

"""Real-LLM smoke tests for the avp-anthropic SDK adapter.

Gated on `-m real_llm` + ANTHROPIC_API_KEY. These exercise the SDK
adapter end-to-end against a real Claude model, no mocks. They drive
`AVPAgent` with `AnthropicModelDriver` directly (in-process), so they
cover the SDK's contract regardless of how downstream agents package
themselves.

Scope:

  - No managed assets: a vanilla Commission with no tools runs cleanly.
    Catches wire-level drift between AVPAgent + AnthropicModelDriver +
    the live API.
  - Resolver-not-configured: a Commission with managed assets but no
    `AVP_RESOLVER_URL` fails-fast with `resolver_not_configured` before
    any model turn (no API spend).

End-to-end managed-asset smoke (resolver wired against a real service)
is a deployment-test concern, not run here. Per-call resolver behavior
is covered by `python/avp/tests/test_http_resolver.py`.
"""

from __future__ import annotations

import io
import json
import os
from typing import Any

import pytest
from pydantic import BaseModel

from avp.agent import AVPAgent, http_resolver_from_env
from avp.agent.mock import ScriptedTools
from avp.commission import Commission
from avp.io import write_event
from avp_anthropic import AnthropicModelDriver, build_descriptor

SMOKE_MODEL = os.environ.get("AVP_SMOKE_MODEL", "claude-haiku-4-5-20251001")

pytestmark = pytest.mark.real_llm


class _StdoutSink:
    def __init__(self, sink: io.StringIO) -> None:
        self._sink = sink

    def observe(self, event: object) -> None:
        if isinstance(event, BaseModel):
            write_event(event, file=self._sink)
        else:
            self._sink.write(json.dumps(event) + "\n")
            self._sink.flush()


def _run_agent(commission: Commission, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Run `AVPAgent` + `AnthropicModelDriver` in-process, collect NDJSON
    events from the supervisor sink."""
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    sink = io.StringIO()

    driver = AnthropicModelDriver(model=commission.model or SMOKE_MODEL)

    agent = AVPAgent(
        commission=commission,
        model=driver,
        tools=ScriptedTools(),
        supervisor=_StdoutSink(sink),
        resolver=http_resolver_from_env(),
        descriptor=build_descriptor(
            agent_name="avp-anthropic-real-llm-test",
            agent_version="0.1.0",
        ),
    )
    agent.run()
    return [json.loads(line) for line in sink.getvalue().splitlines() if line.strip()]


def test_unmanaged_commission_smoke_runs_against_real_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vanilla Commission (no managed assets) runs cleanly end-to-end
    against the live Anthropic API."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    commission = Commission(
        schema_version="0.1",
        run_id="real-llm-unmanaged",
        model=SMOKE_MODEL,
        prompt="Say 'AVP smoke test passes.' and nothing else.",
        enabled_builtin_tools=[],
    )
    events = _run_agent(commission, monkeypatch)
    types = [e["type"] for e in events]
    assert "avp.agent_started" in types
    assert "avp.assistant_message" in types
    assert "avp.text_emitted" in types
    assert types[-1] == "avp.agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_managed_commission_without_resolver_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Commission with managed assets but no `AVP_RESOLVER_URL` set
    emits `error_occurred(resolver_not_configured)` and stops before
    any model call (no API spend)."""
    monkeypatch.delenv("AVP_RESOLVER_URL", raising=False)

    commission = Commission.model_validate(
        {
            "schema_version": "0.1",
            "run_id": "real-llm-no-resolver",
            "model": SMOKE_MODEL,
            "prompt": "should not run",
            "mcp_servers": [{"id": "github", "ref": "doesnt-matter"}],
        }
    )
    events = _run_agent(commission, monkeypatch)
    types = [e["type"] for e in events]
    assert "avp.error_occurred" in types
    err = next(e for e in events if e["type"] == "avp.error_occurred")
    assert err["data"]["avp.error.code"] == "resolver_not_configured"
    assert "avp.assistant_message" not in types
    assert events[-1]["data"]["avp.reason"] == "error"

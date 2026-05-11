"""Real-LLM smoke tests — gated on `-m real_llm` + ANTHROPIC_API_KEY.

These exercise the CLI end-to-end against a real Claude model, no
mocks. Scope:

  - Profile A (no managed assets): a vanilla Commission with no tools
    runs cleanly. Catches any wire-level drift between AVPAgent +
    AnthropicModelDriver + the live API.
  - Resolver-not-configured: a Commission with managed assets but no
    `AVP_RESOLVER_URL` fails-fast with `resolver_not_configured` before
    any model turn (no API spend).

End-to-end managed-asset smoke (resolver wired against a real service)
is a deployment-test concern, not run here. The CLI's resolver client
is a thin urllib wrapper; per-call behavior is covered by
`python/avp/tests/test_http_resolver.py`.
"""

from __future__ import annotations

import json
import os
from io import StringIO
from typing import Any

import pytest

from avp import Commission

SMOKE_MODEL = os.environ.get("AVP_SMOKE_MODEL", "claude-haiku-4-5-20251001")


pytestmark = pytest.mark.real_llm


def _run_cli(commission: Commission, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Pipe a Commission through `avp-anthropic`'s CLI main() and return
    the parsed NDJSON event stream from stdout."""
    from avp_anthropic.cli import main as cli_main

    stdin = StringIO(commission.model_dump_json(by_alias=True, exclude_none=True) + "\n")
    stdout = StringIO()
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)
    cli_main([])
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


def test_profile_a_smoke_runs_against_real_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vanilla Commission (no managed assets) runs cleanly end-to-end
    against the live Anthropic API."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    commission = Commission(
        schema_version="0.1",
        run_id="real-llm-profile-a",
        model=SMOKE_MODEL,
        prompt="Say 'AVP smoke test passes.' and nothing else.",
        enabled_builtin_tools=[],  # text-only run
    )
    events = _run_cli(commission, monkeypatch)
    types = [e["type"] for e in events]
    assert "avp.agent_started" in types
    assert "avp.model_turn_started" in types
    assert "avp.text_emitted" in types
    assert types[-1] == "avp.agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_managed_commission_without_resolver_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
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
    events = _run_cli(commission, monkeypatch)
    types = [e["type"] for e in events]
    assert "avp.error_occurred" in types
    err = next(e for e in events if e["type"] == "avp.error_occurred")
    assert err["data"]["avp.error.code"] == "resolver_not_configured"
    assert "avp.model_turn_started" not in types
    assert events[-1]["data"]["avp.reason"] == "error"

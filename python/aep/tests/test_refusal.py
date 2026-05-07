"""Refusal handling: when the driver detects a refusal-flavored signal
in the model's response, the runner emits `aep.refusal_recorded` and
terminates with `StopReason.refused`.

Universal across providers (Anthropic stop_reason="refusal"|"sensitive",
OpenAI content_filter, Gemini SAFETY/BLOCKLIST/etc.); the AEP wire
normalizes to a provider-agnostic shape with `aep.refusal.reason`,
optional `message`, optional `category`, optional `provider`.
"""

from __future__ import annotations

from aep import Config, StopReason
from aep.runner.drivers import ModelResponse, Refusal
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from aep.runner.runner import AEPRunner
from aep.types import (
    AgentStoppedEvent,
    RefusalRecordedEvent,
    TextEmittedEvent,
)


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


def _runner(model: ScriptedModel) -> AEPRunner:
    cfg = Config(schema_version="0.1", run_id="refusal", model="test/mock")
    return AEPRunner(
        config=cfg,
        model=model,
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )


def _refused_response(refusal: Refusal) -> ModelResponse:
    return ModelResponse(
        tokens_input=10,
        tokens_output=0,
        cost_usd=0.0001,
        duration_ms=1,
        text=None,
        refusal=refusal,
        # The refusal terminates the turn; converged=False because the
        # run didn't reach goal — the runner's StopReason is `refused`,
        # NOT `converged`.
        converged=False,
    )


# ── Wire shape: refusal_recorded carries provider-agnostic fields ──────────


def test_refusal_emits_refusal_recorded_with_full_payload() -> None:
    runner = _runner(
        ScriptedModel(
            [
                _refused_response(
                    Refusal(
                        reason="refusal",
                        message="I can't help with that.",
                        category="harmful_request",
                        provider="anthropic",
                    )
                )
            ]
        )
    )
    runner.run()
    refusals = _by_type(runner.trajectory, RefusalRecordedEvent)
    assert len(refusals) == 1
    r = refusals[0]
    assert r.data.aep_refusal_reason == "refusal"
    assert r.data.aep_refusal_message == "I can't help with that."
    assert r.data.aep_refusal_category == "harmful_request"
    assert r.data.aep_refusal_provider == "anthropic"


def test_refusal_serializes_under_dotted_aliases() -> None:
    runner = _runner(
        ScriptedModel([_refused_response(Refusal(reason="SAFETY", provider="gemini"))])
    )
    runner.run()
    r = _by_type(runner.trajectory, RefusalRecordedEvent)[0]
    wire = r.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert wire["type"] == "aep.refusal_recorded"
    assert wire["data"]["aep.refusal.reason"] == "SAFETY"
    assert wire["data"]["aep.refusal.provider"] == "gemini"
    # Optional fields we didn't set MUST NOT appear on the wire.
    assert "aep.refusal.message" not in wire["data"]
    assert "aep.refusal.category" not in wire["data"]


def test_refusal_terminates_run_with_stop_reason_refused() -> None:
    """The reference runner stops the run on first refusal — a higher-
    level supervisor can choose to reset history and retry, but v0.1
    treats refusal as a hard terminal state for the audit trail."""
    runner = _runner(
        ScriptedModel(
            [
                _refused_response(Refusal(reason="refusal", provider="anthropic")),
                # This second response should NEVER be consumed — the
                # run terminates after the refusal.
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="should not appear",
                    converged=True,
                ),
            ]
        )
    )
    runner.run()
    stopped = _by_type(runner.trajectory, AgentStoppedEvent)[-1]
    assert stopped.data.aep_reason == StopReason.refused
    # The post-refusal text MUST NOT have been emitted.
    texts = [e.data.aep_text for e in _by_type(runner.trajectory, TextEmittedEvent)]
    assert "should not appear" not in texts


def test_refusal_does_not_get_appended_to_history() -> None:
    """A refused turn produced no useful content — adding it to history
    would re-feed the refusal on the next call (if the supervisor
    retries) and pollute audit logs. The runner skips the
    history-append for refused turns."""
    runner = _runner(ScriptedModel([_refused_response(Refusal(reason="refusal"))]))
    runner.run()
    # No assistant turn in history (only the initial system/user turns
    # the runner seeds, which don't include "assistant" by default).
    assistants = [m for m in runner._history if m.get("role") == "assistant"]
    assert assistants == []


def test_no_refusal_field_means_no_refusal_event() -> None:
    """Backwards-compat: a turn without a refusal flag emits no
    refusal_recorded — runner behaviour is unchanged for normal
    completions."""
    runner = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        )
    )
    runner.run()
    assert not _by_type(runner.trajectory, RefusalRecordedEvent)
    stopped = _by_type(runner.trajectory, AgentStoppedEvent)[-1]
    assert stopped.data.aep_reason == StopReason.converged


def test_refusal_recorded_parented_to_turn_span() -> None:
    """Refusal happened during a model turn — parent_span_id is the
    turn span, not the agent root."""
    from aep.types import ModelTurnStartedEvent

    runner = _runner(ScriptedModel([_refused_response(Refusal(reason="refusal"))]))
    runner.run()
    turn_started = _by_type(runner.trajectory, ModelTurnStartedEvent)[0]
    refusal = _by_type(runner.trajectory, RefusalRecordedEvent)[0]
    assert refusal.data.parent_span_id == turn_started.data.span_id


def test_minimal_refusal_only_requires_reason() -> None:
    """`reason` is the only required field — message/category/provider
    are nullable for providers that don't expose them (Anthropic doesn't
    expose a category)."""
    runner = _runner(ScriptedModel([_refused_response(Refusal(reason="refusal"))]))
    runner.run()
    r = _by_type(runner.trajectory, RefusalRecordedEvent)[0]
    assert r.data.aep_refusal_reason == "refusal"
    assert r.data.aep_refusal_message is None
    assert r.data.aep_refusal_category is None
    assert r.data.aep_refusal_provider is None

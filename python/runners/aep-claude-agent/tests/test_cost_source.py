"""CASDK translator cost.source provenance.

Per-turn `model_turn_ended` events get `aep.cost.source=computed`
(we calculate from tokens; the SDK doesn't expose per-turn cost on
AssistantMessage). The reconciliation `cost_recorded` event emitted
when ResultMessage arrives gets `aep.cost.source=reported` because
the SDK's `total_cost_usd` is authoritative truth.

This pins the wire so an audit consumer can:
  - filter `cost.source=reported` to find moments of provider-truth
  - cross-check the running computed total against the reported one
"""

from __future__ import annotations

from typing import Any

from aep import Config, CostRecordedEvent, ModelTurnEndedEvent
from aep_claude_agent.translator import ClaudeAgentTranslator

from .test_translator import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    _client_factory,
    _FakeHookMatcher,
    _FakeOptions,
)


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


def _new_translator(*, sdk_client_cls: Any) -> tuple[ClaudeAgentTranslator, list]:
    cfg = Config(
        schema_version="0.1",
        run_id="cost-source",
        model="claude-sonnet-4-6",
        prompt="hi",
        allowed_tools=["bash"],
    )
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        sdk_client_cls=sdk_client_cls,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


def test_per_turn_model_turn_ended_tagged_computed() -> None:
    """The translator computes cost from tokens (the SDK doesn't expose
    per-turn cost) — every model_turn_ended MUST carry
    `aep.cost.source=computed`."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("done")],
                usage={"input_tokens": 50, "output_tokens": 12},
            ),
            ResultMessage(total_cost_usd=0.0042),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()
    ended = _by_type(out, ModelTurnEndedEvent)
    assert ended
    for e in ended:
        assert e.data.aep_cost_source == "computed"


def test_reconciliation_cost_recorded_tagged_reported() -> None:
    """When ResultMessage arrives with `total_cost_usd`, the translator
    emits a final `cost_recorded` reconciliation event tagged
    `aep.cost.source=reported` so audit consumers see the moment we
    flipped from computed estimate to provider-truth."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("done")],
                usage={"input_tokens": 50, "output_tokens": 12},
            ),
            ResultMessage(total_cost_usd=0.0042),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()
    cost_events = _by_type(out, CostRecordedEvent)
    # The reconciliation event MUST be present and tagged reported.
    reported = [e for e in cost_events if e.data.aep_cost_source == "reported"]
    assert len(reported) == 1
    snap = reported[0].data.aep_state
    assert abs(snap.total_cost_usd - 0.0042) < 1e-9


def test_reconciliation_event_serializes_under_dotted_alias() -> None:
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("ok")],
                usage={"input_tokens": 5, "output_tokens": 5},
            ),
            ResultMessage(total_cost_usd=0.0001),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()
    reported = next(
        e for e in _by_type(out, CostRecordedEvent) if e.data.aep_cost_source == "reported"
    )
    wire = reported.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert wire["data"]["aep.cost.source"] == "reported"


def test_no_result_message_means_no_reported_event() -> None:
    """If the SDK never emits ResultMessage (e.g. abrupt disconnect),
    no reconciliation event fires and there's no `reported` cost on
    the wire — the running computed total stays the best we have."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("ok")],
                usage={"input_tokens": 5, "output_tokens": 5},
            )
            # No ResultMessage.
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()
    cost_events = _by_type(out, CostRecordedEvent)
    reported = [e for e in cost_events if e.data.aep_cost_source == "reported"]
    assert reported == []

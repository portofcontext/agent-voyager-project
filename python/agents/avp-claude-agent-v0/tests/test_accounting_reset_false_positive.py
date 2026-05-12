"""Regression: don't fire `error_occurred(accounting_reset)` when an
AssistantMessage simply carries no usage data.

Found in production: every successful run that involves tool calls was
emitting a spurious `error_occurred(accounting_reset)` event because the
Claude Agent SDK emits follow-up AssistantMessages (around tool results)
with `usage=None`. The translator's `_compute_cost` returned all zeros
for those, and the cumulative-drop guard read `0 < <prev>` as a
"cumulative dropped without baseline reset" signal.

Truth: cumulative didn't drop; that message just had no usage attached.
The fix distinguishes "no usage on this message" from "actual SDK
cumulative regression" — the former skips both reset-detection and
turn emission; the latter still triggers `accounting_reset` (it's still
the legitimate signal we built the guard for).
"""

from __future__ import annotations

from avp import Commission
from avp.types import ErrorOccurredEvent, ModelTurnEndedEvent
from avp_claude_agent.translator import ClaudeAgentTranslator

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


def _new_translator(*, sdk_client_cls):
    cfg = Commission(
        schema_version="0.1",
        run_id="acct-reset",
        model="claude-sonnet-4-6",
        prompt="hi",
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


def test_no_accounting_reset_when_followup_message_has_no_usage() -> None:
    """The reproduction case from the audit:
      - Turn 1: AssistantMessage with TextBlock + usage carrying real
        token counts (the actual model call).
      - 'Turn 2': AssistantMessage with NO usage and NO text content
        (a follow-up the SDK emits around tool processing).
      - ResultMessage closes the run.

    Pre-fix: the second AssistantMessage triggered
    `error_occurred(accounting_reset)`. Post-fix: it's recognized as a
    non-turn carrier and silently skipped, the run completes clean."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("answer")],
                usage={"input_tokens": 1234, "output_tokens": 56},
            ),
            # The follow-up: SDK quirk, no usage, no content.
            AssistantMessage(content=[], usage=None),
            ResultMessage(total_cost_usd=0.005),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()

    assert _by_type(out, ErrorOccurredEvent) == []
    # And exactly one real turn was counted, not two.
    assert len(_by_type(out, ModelTurnEndedEvent)) == 1


def test_no_accounting_reset_when_followup_has_zero_usage_dict() -> None:
    """Some SDK versions return `usage={}` or all-zero usage rather than
    `usage=None`. Both shapes mean 'no fresh model call here'; both
    should be treated identically."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("answer")],
                usage={"input_tokens": 100, "output_tokens": 10},
            ),
            AssistantMessage(
                content=[],
                usage={"input_tokens": 0, "output_tokens": 0},
            ),
            ResultMessage(total_cost_usd=0.001),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()
    assert _by_type(out, ErrorOccurredEvent) == []


def test_accounting_reset_still_fires_on_real_cumulative_drop() -> None:
    """The guard's legitimate purpose: when the SDK's cumulative truly
    drops AND the message carries fresh content (so it's a real turn),
    we still emit `accounting_reset`. The fix narrows the false-positive
    case (no-usage follow-ups) without removing the real signal.

    Reproduction: turn 1 builds up cumulative input=1000. Turn 2
    arrives with FRESH content (TextBlock) AND usage that's lower than
    the previous cumulative (input=500) — that's a true regression."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("first")],
                usage={"input_tokens": 1000, "output_tokens": 50},
            ),
            AssistantMessage(
                content=[TextBlock("second")],
                # Cumulative DROPPED to 500 — the real signal we want.
                usage={"input_tokens": 500, "output_tokens": 30},
            ),
            ResultMessage(total_cost_usd=0.01),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()
    errors = _by_type(out, ErrorOccurredEvent)
    assert len(errors) == 1
    assert errors[0].data.avp_error_code == "accounting_reset"


def test_followup_without_usage_does_not_increment_step() -> None:
    """The non-turn-carrier message MUST NOT bump `_step`. Pre-fix the
    accounting_reset emit happened BEFORE the is_real_turn check, so
    the spurious error was the only side effect — but we should also
    pin that the step counter stays at 1 for a 1-real-turn run with
    a no-usage follow-up."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("answer")],
                usage={"input_tokens": 100, "output_tokens": 10},
            ),
            AssistantMessage(content=[], usage=None),
            ResultMessage(total_cost_usd=0.001),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    t.run()
    ended = _by_type(out, ModelTurnEndedEvent)
    assert len(ended) == 1
    assert ended[0].data.step == 1

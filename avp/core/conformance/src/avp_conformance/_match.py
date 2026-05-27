"""Match an emitted trajectory against a case's `Expectations`.

The trajectory is a list of event dicts (parsed NDJSON, canonical wire
shape: `type`, `source`, `data` with dotted `avp.*` keys). Matching is
structural and partial: a matcher's `match` dict must be a deep-partial
subset of some event. `final_state` totals are computed by folding the
stream, because `agent_stopped` deliberately carries no cumulative totals
(spec: consumers derive them from `assistant_message` events).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from avp_conformance.case import EventMatcher, Expectations, FinalState

T_ASSISTANT_MESSAGE = "avp.assistant_message"
T_AGENT_STOPPED = "avp.agent_stopped"


@dataclass
class MatchResult:
    """Outcome of matching one case. `reasons` lists every failure."""

    ok: bool
    reasons: list[str] = field(default_factory=list)


def _partial(value: Any, pattern: Any) -> bool:
    """True if `pattern` is a deep-partial subset of `value`.

    Dicts: every key in `pattern` must be present in `value` and match
    (recursively); extra keys in `value` are ignored. Lists: same length,
    element-wise partial. Scalars: exact equality.

    Operator: a pattern `{"$contains": X}` matches a list `value` when at
    least one element partial-matches `X`. Use it to assert presence within
    an order-/length-variable list (e.g. a text block in `avp.content`, an
    MCP server in `avp.mcp_servers`) without pinning the whole list.
    """
    if isinstance(pattern, dict):
        if set(pattern) == {"$contains"}:
            return isinstance(value, list) and any(
                _partial(elem, pattern["$contains"]) for elem in value
            )
        if not isinstance(value, dict):
            return False
        return all(k in value and _partial(value[k], v) for k, v in pattern.items())
    if isinstance(pattern, list):
        if not isinstance(value, list) or len(value) != len(pattern):
            return False
        return all(_partial(v, p) for v, p in zip(value, pattern, strict=True))
    return value == pattern


def _label(m: EventMatcher) -> str:
    """Human-readable identifier for a matcher in failure messages."""
    if m.label:
        return m.label
    return m.match.get("type", str(m.match))


def _match_subsequence(events: list[dict], matchers: list[EventMatcher]) -> int | None:
    """Each matcher matches a later event than the previous (gaps allowed).
    Returns the index of the first matcher that can't be placed, else None."""
    idx = 0
    for i, m in enumerate(matchers):
        while idx < len(events) and not _partial(events[idx], m.match):
            idx += 1
        if idx >= len(events):
            return i
        idx += 1
    return None


def _match_strict(events: list[dict], matchers: list[EventMatcher]) -> int | None:
    """Matchers must align to a contiguous run of events, in order.
    Returns None on success, 0 to flag the (whole) block as unmatched."""
    n = len(matchers)
    if n == 0:
        return None
    for start in range(len(events) - n + 1):
        if all(_partial(events[start + j], matchers[j].match) for j in range(n)):
            return None
    return 0


def _match_any(events: list[dict], matchers: list[EventMatcher]) -> int | None:
    """Each matcher matches some event, order irrelevant.
    Returns the index of the first matcher with no match, else None."""
    for i, m in enumerate(matchers):
        if not any(_partial(e, m.match) for e in events):
            return i
    return None


def _check_final_state(events: list[dict], fs: FinalState) -> list[str]:
    """Verify the terminal event + folded totals against `final_state`."""
    reasons: list[str] = []

    stopped = [e for e in events if e.get("type") == T_AGENT_STOPPED]
    if fs.stop_reason is not None:
        if not stopped:
            reasons.append("final_state.stop_reason: no agent_stopped event emitted")
        else:
            actual = stopped[-1].get("data", {}).get("avp.reason")
            if actual != fs.stop_reason.value:
                reasons.append(
                    f"final_state.stop_reason: expected {fs.stop_reason.value!r}, got {actual!r}"
                )

    assistants = [e for e in events if e.get("type") == T_ASSISTANT_MESSAGE]
    if fs.total_turns is not None and len(assistants) != fs.total_turns:
        reasons.append(f"final_state.total_turns: expected {fs.total_turns}, got {len(assistants)}")

    if _wants_tokens(fs):
        total_tokens = 0
        for e in assistants:
            usage = e.get("data", {}).get("avp.usage", {})
            total_tokens += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        if fs.min_total_tokens is not None and total_tokens < fs.min_total_tokens:
            reasons.append(f"final_state.min_total_tokens: {total_tokens} < {fs.min_total_tokens}")
        if fs.max_total_tokens is not None and total_tokens > fs.max_total_tokens:
            reasons.append(f"final_state.max_total_tokens: {total_tokens} > {fs.max_total_tokens}")

    if _wants_cost(fs):
        total_cost = sum(float(e.get("data", {}).get("avp.cost_usd", 0.0)) for e in assistants)
        if fs.min_total_cost_usd is not None and total_cost < fs.min_total_cost_usd:
            reasons.append(
                f"final_state.min_total_cost_usd: {total_cost} < {fs.min_total_cost_usd}"
            )
        if fs.max_total_cost_usd is not None and total_cost > fs.max_total_cost_usd:
            reasons.append(
                f"final_state.max_total_cost_usd: {total_cost} > {fs.max_total_cost_usd}"
            )

    return reasons


def _wants_tokens(fs: FinalState) -> bool:
    return fs.min_total_tokens is not None or fs.max_total_tokens is not None


def _wants_cost(fs: FinalState) -> bool:
    return fs.min_total_cost_usd is not None or fs.max_total_cost_usd is not None


def match_case(events: list[dict], expectations: Expectations) -> MatchResult:
    """Match an emitted trajectory against a case's expectations.

    Checks, in order: positive `events` per `ordering`, `forbidden_events`
    (none may appear), and `final_state`. Collects every failure into one
    `MatchResult` so a run surfaces all problems at once.
    """
    reasons: list[str] = []

    dispatch = {
        "in_order_subsequence": _match_subsequence,
        "in_order_strict": _match_strict,
        "any_order": _match_any,
    }
    failed = dispatch[expectations.ordering](events, expectations.events)
    if failed is not None:
        if expectations.ordering == "in_order_strict":
            labels = ", ".join(_label(m) for m in expectations.events)
            reasons.append(
                f"events ({expectations.ordering}): no contiguous run matched [{labels}]"
            )
        else:
            m = expectations.events[failed]
            reasons.append(f"events ({expectations.ordering}): unmatched matcher {_label(m)!r}")

    for m in expectations.forbidden_events:
        if any(_partial(e, m.match) for e in events):
            reasons.append(f"forbidden_events: {_label(m)!r} appeared but must not")

    if expectations.final_state is not None:
        reasons.extend(_check_final_state(events, expectations.final_state))

    return MatchResult(ok=not reasons, reasons=reasons)

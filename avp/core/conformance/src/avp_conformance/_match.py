"""Match an emitted trajectory against a case's `Expectations`.

The trajectory is a list of event dicts (parsed NDJSON, canonical wire
shape: `type`, `source`, `data` with dotted `avp.*` keys). Matching is
structural and partial: a matcher's `match` dict must be a deep-partial
subset of some event. `final_state` totals are computed by folding the
stream, because `agent_stopped` deliberately carries no cumulative totals
(spec: consumers derive them from `assistant_message` events).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from avp_conformance.case import EventMatcher, Expectations, FinalState

T_ASSISTANT_MESSAGE = "avp.assistant_message"
T_AGENT_STOPPED = "avp.agent_stopped"

# OTel span identification (FOUNDATIONS.md): trace_id is 32 hex chars, span_id
# is 16. ZERO_SPAN is the root sentinel (no parent).
_TRACE_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_RE = re.compile(r"^[0-9a-f]{16}$")
_ZERO_SPAN = "0" * 16
# Prelude events anchor the trajectory at the root (no parent span).
_ROOT_TYPES = frozenset({"avp.run_requested", "avp.agent_described", "avp.agent_started"})


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


def _check_structure(events: list[dict]) -> list[str]:
    """Universal span-tree invariants every conforming trajectory MUST satisfy,
    independent of the case (OTel span identification, FOUNDATIONS.md):

    - one `trace_id` for the whole run;
    - every event's `span_id` / `parent_span_id` is well-formed (16 hex), and
      `span_id` is non-zero (each event owns a real span);
    - prelude events (`run_requested`, `agent_described`, `agent_started`) sit
      at the root (`parent_span_id` == zero);
    - every other event's `parent_span_id` either is the root or resolves to a
      span some event in the run actually emitted (the tree has no dangling
      parents). This is what pairs `tool_returned` under its `tool_invoked`,
      turns under the agent span, etc.
    - every `subagent_invoked` frame is closed by a `subagent_returned` with
      the same `span_id`, and a run that abandoned a subagent does not then
      claim it converged (trajectory.md §5.6, criteria 7).

    Run on every checked trajectory, so it guards all cases at once.
    """
    if not events:
        return ["structure: empty trajectory"]

    reasons: list[str] = []
    trace_ids: set[str] = set()
    span_ids: set[str] = set()

    for e in events:
        t = e.get("type", "?")
        d = e.get("data", {}) if isinstance(e.get("data"), dict) else {}
        tid, sid, pid = d.get("trace_id"), d.get("span_id"), d.get("parent_span_id")

        if isinstance(tid, str) and _TRACE_RE.match(tid):
            trace_ids.add(tid)
        else:
            reasons.append(f"structure: {t} has malformed trace_id {tid!r}")

        if isinstance(sid, str) and _SPAN_RE.match(sid):
            if sid == _ZERO_SPAN:
                reasons.append(f"structure: {t} has zero span_id")
            else:
                span_ids.add(sid)
        else:
            reasons.append(f"structure: {t} has malformed span_id {sid!r}")

        if not (isinstance(pid, str) and _SPAN_RE.match(pid)):
            reasons.append(f"structure: {t} has malformed parent_span_id {pid!r}")

    if len(trace_ids) > 1:
        reasons.append(f"structure: multiple trace_ids in one run: {sorted(trace_ids)}")

    for e in events:
        t = e.get("type", "?")
        pid = (e.get("data") or {}).get("parent_span_id")
        if t in _ROOT_TYPES:
            if pid != _ZERO_SPAN:
                reasons.append(f"structure: {t} must be root (parent_span_id == zero), got {pid!r}")
        elif (
            isinstance(pid, str)
            and _SPAN_RE.match(pid)
            and pid != _ZERO_SPAN
            and pid not in span_ids
        ):
            reasons.append(f"structure: {t} parent_span_id {pid!r} resolves to no emitted span")

    reasons.extend(_check_subagent_frames(events))
    return reasons


def _check_subagent_frames(events: list[dict]) -> list[str]:
    """Every subagent frame opened must be closed, and an abandoned frame
    must not coexist with a `converged` run.

    An unclosed frame is how an asynchronously-dispatched subagent silently
    disappears: the launch receipt returns in milliseconds, the parent stops
    before the child reports, and without this the trajectory looks complete
    while the delegated work simply vanished.
    """
    reasons: list[str] = []
    opened: dict[str, str] = {}
    closed: set[str] = set()
    abandoned = False

    for e in events:
        t = e.get("type")
        d = e.get("data", {}) if isinstance(e.get("data"), dict) else {}
        sid = d.get("span_id")
        if not isinstance(sid, str):
            continue
        if t == "avp.subagent_invoked":
            opened[sid] = d.get("avp.subagent.name") or "?"
        elif t == "avp.subagent_returned":
            closed.add(sid)
            if d.get("avp.subagent.reason") == "abandoned":
                abandoned = True

    for sid, name in opened.items():
        if sid not in closed:
            reasons.append(
                f"structure: subagent_invoked {name!r} (span {sid}) has no matching "
                "subagent_returned; the frame was left open at run end"
            )

    if abandoned:
        stopped = [e for e in events if e.get("type") == "avp.agent_stopped"]
        for e in stopped:
            actual = (e.get("data") or {}).get("avp.reason")
            if actual == "converged":
                reasons.append(
                    "structure: run abandoned a subagent but reports agent_stopped(converged)"
                )

    return reasons


def match_case(events: list[dict], expectations: Expectations) -> MatchResult:
    """Match an emitted trajectory against a case's expectations.

    Checks, in order: universal span-tree structure, positive `events` per
    `ordering`, `forbidden_events` (none may appear), and `final_state`.
    Collects every failure into one `MatchResult` so a run surfaces all
    problems at once.
    """
    reasons: list[str] = _check_structure(events)

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

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
from functools import cache
from typing import Any

from avp.pricing import COST_SOURCE_UNKNOWN, PriceTable, compute_cost, load_default_prices
from avp_conformance.case import EventMatcher, Expectations, FinalState, ToolCallMatcher

T_ASSISTANT_MESSAGE = "avp.assistant_message"
T_AGENT_STOPPED = "avp.agent_stopped"
T_TOOL_INVOKED = "avp.tool_invoked"
T_TOOL_RETURNED = "avp.tool_returned"

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
    `{"$text_contains": "text"}` searches a string or the text blocks in a
    content list, accommodating both valid tool-result representations.
    """
    if isinstance(pattern, dict):
        if set(pattern) == {"$text_contains"}:
            needle = pattern["$text_contains"]
            if not isinstance(needle, str):
                return False
            if isinstance(value, str):
                return needle in value
            return isinstance(value, list) and any(
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
                and needle in block["text"]
                for block in value
            )
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


def _match_tool_call(events: list[dict], call: ToolCallMatcher) -> bool:
    """Some call's `tool_invoked` matches `call.invoked` and its own
    `tool_returned` matches `call.returned`."""
    returned = {
        (e.get("data") or {}).get("avp.tool.call_id"): e.get("data") or {}
        for e in events
        if e.get("type") == T_TOOL_RETURNED
    }
    return any(
        _partial(e.get("data") or {}, call.invoked)
        and _partial(returned.get((e.get("data") or {}).get("avp.tool.call_id"), {}), call.returned)
        for e in events
        if e.get("type") == T_TOOL_INVOKED
    )


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
    reasons.extend(_check_tool_pairing(events))
    return reasons


def _check_tool_pairing(events: list[dict]) -> list[str]:
    """Every tool call is one `tool_invoked` and, once it ran, one
    `tool_returned` carrying its own result (trajectory.md §8 rule 4):

    - each `tool_use` block in a turn's content has exactly one `tool_invoked`
      with that call id, under that turn;
    - each `tool_returned` sits under the `tool_invoked` with its call id, and
      its `tool_result.tool_use_id` is that call id;
    - no call returns twice, and in a converged run every call returned. An
      interrupted or failed run may stop with a call still in flight.

    Parallel calls are where translators pair results by position or batch
    instead of by id; these catch it on every case.
    """
    reasons: list[str] = []
    uses: dict[str, str] = {}
    for e in events:
        if e.get("type") != T_ASSISTANT_MESSAGE:
            continue
        d = e.get("data") or {}
        for block in d.get("avp.content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses[block.get("id")] = d.get("span_id")
    invoked: dict[str, dict] = {}
    for e in events:
        if e.get("type") != T_TOOL_INVOKED:
            continue
        d = e.get("data") or {}
        call = d.get("avp.tool.call_id")
        if call in invoked:
            reasons.append(f"tools: call {call!r} has more than one tool_invoked")
            continue
        invoked[call] = d
        if call not in uses:
            reasons.append(f"tools: tool_invoked {call!r} has no tool_use block in any turn")
        elif d.get("parent_span_id") != uses[call]:
            reasons.append(f"tools: tool_invoked {call!r} is not under the turn that called it")
    for call in uses.keys() - invoked.keys():
        reasons.append(f"tools: tool_use {call!r} has no tool_invoked")
    returned: set[str] = set()
    for e in events:
        if e.get("type") != T_TOOL_RETURNED:
            continue
        d = e.get("data") or {}
        call = d.get("avp.tool.call_id")
        result_id = (d.get("avp.tool_result") or {}).get("tool_use_id")
        if call not in invoked:
            reasons.append(f"tools: tool_returned {call!r} has no tool_invoked")
            continue
        if call in returned:
            reasons.append(f"tools: call {call!r} returned more than once")
        returned.add(call)
        if d.get("parent_span_id") != invoked[call].get("span_id"):
            reasons.append(f"tools: tool_returned {call!r} is not under its tool_invoked")
        if result_id != call:
            reasons.append(f"tools: tool_returned {call!r} carries the result for {result_id!r}")
    stopped = [e for e in events if e.get("type") == T_AGENT_STOPPED]
    if stopped and (stopped[-1].get("data") or {}).get("avp.reason") == "converged":
        for call in invoked.keys() - returned:
            reasons.append(f"tools: call {call!r} never returned in a converged run")
    return reasons


@cache
def _prices() -> PriceTable:
    return load_default_prices()


# A computed cost may differ from the harness's recomputation by float noise
# and by rounding an agent applies, never by a pricing mistake.
_COST_REL_TOL = 1e-6
_COST_ABS_TOL = 1e-9


def _check_accounting(events: list[dict]) -> list[str]:
    """Per-turn accounting every conforming trajectory MUST satisfy
    (trajectory.md §3.3), checked on every case:

    - token counts are non-negative integers, and the cache split is inside
      `input_tokens` (`cache_read + cache_creation <= input_tokens`);
    - `avp.cost_usd` is non-negative, and zero when `avp.cost.source` is
      `unknown`;
    - a `computed` cost equals the bundled price table's cost for the turn's
      usage, priced as the response model, else the request model (the
      Recorder's fallback for dated snapshot ids). A turn whose models the
      table doesn't know can't be recomputed and is not judged.

    Catches the accounting bugs presence checks miss: double-counted cache
    tokens, a cache split outside the input total, mis-priced turns.
    """
    reasons: list[str] = []
    for e in events:
        if e.get("type") != T_ASSISTANT_MESSAGE:
            continue
        d = e.get("data") or {}
        step = d.get("avp.step", "?")
        where = f"accounting: assistant_message step {step}"
        usage = d.get("avp.usage") or {}
        counts = {
            k: usage.get(k)
            for k in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
                "reasoning_output_tokens",
            )
            if usage.get(k) is not None
        }
        bad = {k: v for k, v in counts.items() if not (isinstance(v, int) and v >= 0)}
        if bad:
            reasons.append(f"{where}: token counts must be non-negative integers, got {bad}")
            continue
        inp = counts.get("input_tokens", 0)
        cached = counts.get("cache_read_input_tokens", 0) + counts.get(
            "cache_creation_input_tokens", 0
        )
        if cached > inp:
            reasons.append(
                f"{where}: cache_read + cache_creation ({cached}) exceeds input_tokens ({inp});"
                " input_tokens must include the cache split"
            )
        cost = d.get("avp.cost_usd")
        source = d.get("avp.cost.source")
        if not isinstance(cost, int | float) or cost < 0:
            reasons.append(f"{where}: avp.cost_usd must be a non-negative number, got {cost!r}")
            continue
        if source == COST_SOURCE_UNKNOWN and cost != 0:
            reasons.append(f"{where}: avp.cost.source is unknown but avp.cost_usd is {cost}")
        if source != "computed":
            continue
        expected = _recompute_cost(d, counts)
        if expected is not None and abs(cost - expected) > max(
            _COST_ABS_TOL, _COST_REL_TOL * expected
        ):
            reasons.append(
                f"{where}: computed avp.cost_usd {cost} != {expected} from the price table"
                f" for {d.get('avp.response.model') or d.get('avp.request.model')!r} and its usage"
            )
    return reasons


def _recompute_cost(data: dict, counts: dict[str, int]) -> float | None:
    """The turn's cost from the bundled price table, or None when neither
    model is priced there."""
    provider = data.get("avp.provider.name")
    for model in dict.fromkeys(
        m for m in (data.get("avp.response.model"), data.get("avp.request.model")) if m
    ):
        cost, source = compute_cost(
            model,
            provider=provider,
            input_tokens=counts.get("input_tokens", 0),
            output_tokens=counts.get("output_tokens", 0),
            cache_read=counts.get("cache_read_input_tokens", 0),
            cache_write=counts.get("cache_creation_input_tokens", 0),
            prices=_prices(),
        )
        if source != COST_SOURCE_UNKNOWN:
            return cost
    return None


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

    Checks, in order: universal span-tree structure and accounting, positive `events` per
    `ordering`, `forbidden_events` (none may appear), and `final_state`.
    Collects every failure into one `MatchResult` so a run surfaces all
    problems at once.
    """
    reasons: list[str] = [*_check_structure(events), *_check_accounting(events)]

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

    for call in expectations.tool_calls:
        if not _match_tool_call(events, call):
            reasons.append(f"tool_calls: no call matched {call.label or call.invoked!r}")

    for m in expectations.forbidden_events:
        if any(_partial(e, m.match) for e in events):
            reasons.append(f"forbidden_events: {_label(m)!r} appeared but must not")

    if expectations.final_state is not None:
        reasons.extend(_check_final_state(events, expectations.final_state))

    return MatchResult(ok=not reasons, reasons=reasons)

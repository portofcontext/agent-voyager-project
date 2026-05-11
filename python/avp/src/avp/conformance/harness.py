"""Load and execute one AVP v0.1 conformance case end-to-end."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avp.agent.agent import AVPAgent
from avp.agent.mock import (
    ScriptedResolver,
    ScriptedSupervisor,
    ScriptedTools,
    parse_scripted_model,
)
from avp.conformance.matcher import matches_partial
from avp.types import AgentDescriptor, Commission

# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class CaseFailure:
    label: str
    detail: str


@dataclass
class CaseResult:
    case_id: str
    path: Path
    passed: bool
    failures: list[CaseFailure] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0


# ── Trajectory helpers ────────────────────────────────────────────────────────


def _trajectory_to_dicts(traj: list[BaseModel | dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in traj:
        if isinstance(ev, BaseModel):
            # by_alias=True emits dotted wire keys (e.g. gen_ai.usage.input_tokens,
            # avp.cost_usd) so case expectations can match the on-the-wire shape.
            out.append(ev.model_dump(mode="json", by_alias=True, exclude_none=True))
        else:
            out.append(dict(ev))
    return out


def _check_in_order_subsequence(
    matchers: list[dict[str, Any]], events: list[dict[str, Any]]
) -> tuple[bool, str]:
    """Each matcher must match an event after the previous matcher's match."""
    cursor = 0
    for i, m in enumerate(matchers):
        pattern = m["match"]
        label = m.get("label") or f"matcher #{i + 1} {pattern}"
        found = None
        for j in range(cursor, len(events)):
            if matches_partial(pattern, events[j]):
                found = j
                break
        if found is None:
            return False, f"expected event matching {label}; not found after position {cursor}"
        cursor = found + 1
    return True, ""


def _check_in_order_strict(
    matchers: list[dict[str, Any]], events: list[dict[str, Any]]
) -> tuple[bool, str]:
    if len(matchers) != len(events):
        return False, f"expected exactly {len(matchers)} events, got {len(events)}"
    for i, (m, ev) in enumerate(zip(matchers, events, strict=False)):
        pattern = m["match"]
        if not matches_partial(pattern, ev):
            label = m.get("label") or f"matcher #{i + 1}"
            return False, f"event {i} did not match {label}: pattern={pattern}, got={ev}"
    return True, ""


def _check_any_order(
    matchers: list[dict[str, Any]], events: list[dict[str, Any]]
) -> tuple[bool, str]:
    used: set[int] = set()
    for i, m in enumerate(matchers):
        pattern = m["match"]
        label = m.get("label") or f"matcher #{i + 1} {pattern}"
        found = None
        for j, ev in enumerate(events):
            if j in used:
                continue
            if matches_partial(pattern, ev):
                found = j
                break
        if found is None:
            return False, f"no event matched {label}"
        used.add(found)
    return True, ""


_ORDERING_FNS = {
    "in_order_subsequence": _check_in_order_subsequence,
    "in_order_strict": _check_in_order_strict,
    "any_order": _check_any_order,
}


# ── Final state assertion ────────────────────────────────────────────────────


def _final_state(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for ev in reversed(events):
        if ev.get("type") == "avp.agent_stopped":
            return ev
    return None


def _check_final_state(expected: dict[str, Any], events: list[dict[str, Any]]) -> tuple[bool, str]:
    stop = _final_state(events)
    if stop is None:
        return False, "avp.agent_stopped not found in trajectory"

    data = stop.get("data") or {}
    snap = data.get("avp.state") or {}
    failures: list[str] = []

    if "stop_reason" in expected and data.get("avp.reason") != expected["stop_reason"]:
        failures.append(
            f"final_state.stop_reason: expected {expected['stop_reason']!r}, "
            f"got {data.get('avp.reason')!r}"
        )
    if "total_turns" in expected:
        actual = snap.get("total_turns", data.get("avp.total_turns"))
        if actual != expected["total_turns"]:
            failures.append(
                f"final_state.total_turns: expected {expected['total_turns']}, got {actual}"
            )
    for k, op in (
        ("min_total_cost_usd", lambda a, e: a + 1e-9 < e),
        ("max_total_cost_usd", lambda a, e: a > e + 1e-9),
        ("min_total_tokens", lambda a, e: a < e),
        ("max_total_tokens", lambda a, e: a > e),
    ):
        if k not in expected:
            continue
        is_cost = "cost" in k
        snap_key = "total_cost_usd" if is_cost else "total_tokens"
        env_key = "avp.total_cost_usd" if is_cost else "avp.total_tokens"
        actual = snap.get(snap_key, data.get(env_key))
        if actual is None:
            failures.append(f"final_state.{k}: missing {snap_key} in agent_stopped.data.avp.state")
            continue
        if op(actual, expected[k]):
            failures.append(
                f"final_state.{k}: bound {expected[k]} violated by actual {snap_key}={actual}"
            )

    if failures:
        return False, "; ".join(failures)
    return True, ""


# ── Run one case ─────────────────────────────────────────────────────────────


def _build_agent(case: dict[str, Any]) -> AVPAgent:
    commission = Commission.model_validate(case["commission"])
    model = parse_scripted_model(case.get("scripted_model", []))
    tools = ScriptedTools(case.get("scripted_tools") or {})
    supervisor = ScriptedSupervisor(case.get("scripted_supervisor") or [])
    builtin_tools = case.get("agent_builtin_tools") or None
    # `scripted_resolver` configures the in-process ResolverDriver the
    # AVPAgent uses to dereference Commission-managed refs. Two keys:
    #
    #   "resolutions": maps "<kind>:<id>" (or just "<id>") → either
    #     {"result": <material>} or {"error": "...", "error_code": "..."}.
    #   "subagent_spawns": maps subagent id → canned SubagentSpawnOutcome
    #     fields (child_run_id, text, reason, usage, duration_ms, error?).
    #
    # When the Commission has any managed assets and the case omits
    # `scripted_resolver`, the harness still wires a ScriptedResolver:
    # the resolver will raise on every lookup, exercising the
    # `managed_ref_resolve_failed` path. Cases that want a run with no
    # managed assets leave the Commission lists empty and need no
    # resolver.
    sr_cfg = case.get("scripted_resolver") or {}
    has_managed = bool(commission.mcp_servers or commission.skills or commission.subagents)
    resolver: ScriptedResolver | None
    if has_managed and not case.get("omit_resolver"):
        resolver = ScriptedResolver(
            resolutions=sr_cfg.get("resolutions") or {},
            subagent_spawns=sr_cfg.get("subagent_spawns") or {},
        )
    else:
        # Either no managed assets, or the case wants to exercise the
        # `resolver_not_configured` startup gate (omit_resolver=true).
        resolver = None
    # When the case ships an `agent_descriptor`, the agent emits the
    # `run_requested` + `agent_described` prelude. Cases not exercising
    # the prelude omit the field — the agent skips emission and the rest
    # of the trajectory looks the same as before this field existed.
    descriptor_dict = case.get("agent_descriptor")
    descriptor = AgentDescriptor.model_validate(descriptor_dict) if descriptor_dict else None
    return AVPAgent(
        commission=commission,
        model=model,
        tools=tools,
        supervisor=supervisor,
        agent_builtin_tools=builtin_tools,
        resolver=resolver,
        descriptor=descriptor,
    )


def run_case(path: Path) -> CaseResult:
    """Execute one case file and return a CaseResult."""
    import time as _time

    case = json.loads(path.read_text())
    case_id = case.get("id") or path.stem
    failures: list[CaseFailure] = []
    trajectory_dicts: list[dict[str, Any]] = []

    t0 = _time.monotonic()
    try:
        agent = _build_agent(case)
        agent.run()
        trajectory_dicts = _trajectory_to_dicts(agent.trajectory)
    except Exception as exc:
        failures.append(
            CaseFailure(
                label="agent-error",
                detail=f"{type(exc).__name__}: {exc}",
            )
        )
        return CaseResult(
            case_id=case_id,
            path=path,
            passed=False,
            failures=failures,
            trajectory=trajectory_dicts,
            duration_ms=int((_time.monotonic() - t0) * 1000),
        )

    expectations = case["expectations"]
    matchers = expectations["events"]
    ordering = expectations.get("ordering", "in_order_subsequence")
    fn = _ORDERING_FNS.get(ordering)
    if fn is None:
        failures.append(
            CaseFailure(
                label="harness-bug",
                detail=f"unknown ordering mode {ordering!r}",
            )
        )
    else:
        ok, msg = fn(matchers, trajectory_dicts)
        if not ok:
            failures.append(CaseFailure(label=f"events ({ordering})", detail=msg))

    for fb in expectations.get("forbidden_events") or []:
        pattern = fb["match"]
        for ev in trajectory_dicts:
            if matches_partial(pattern, ev):
                label = fb.get("label") or "forbidden_events"
                failures.append(
                    CaseFailure(
                        label=f"forbidden: {label}",
                        detail=f"event matched: {ev}",
                    )
                )
                break

    if "final_state" in expectations:
        ok, msg = _check_final_state(expectations["final_state"], trajectory_dicts)
        if not ok:
            failures.append(CaseFailure(label="final_state", detail=msg))

    return CaseResult(
        case_id=case_id,
        path=path,
        passed=not failures,
        failures=failures,
        trajectory=trajectory_dicts,
        duration_ms=int((_time.monotonic() - t0) * 1000),
    )


def run_suite(cases_dir: Path) -> list[CaseResult]:
    """Execute every *.json case under cases_dir, recursively."""
    paths = sorted(cases_dir.rglob("*.json"))
    return [run_case(p) for p in paths]

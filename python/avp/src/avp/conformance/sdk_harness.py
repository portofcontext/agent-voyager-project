"""Framework for per-SDK conformance harnesses.

A per-SDK harness implements one function:

    def run_one(case: dict[str, Any]) -> list[BaseModel]:
        '''Build the SDK's agent for `case`, run it, return the events
        it emitted. May raise; the framework catches and reports.'''

The framework provides everything else — case loading, expectation
evaluation against `case.expectations.events / forbidden_events /
final_state`, ordering modes (`in_order_subsequence`, `in_order_strict`,
`any_order`), CaseResult construction, recursive suite iteration, and a
CLI with the same flag surface as `avp-conformance run`.

Adding a new SDK harness:

    from avp.conformance.sdk_harness import make_cli, run_case, run_suite

    def _run_one(case):
        agent = _build_my_agent(case)   # SDK-specific
        events = []
        agent.run()                      # or however the SDK runs
        return events

    main = make_cli(
        runner=_run_one, prog="my-sdk-conformance", description="..."
    )

    # And a console-script entry in pyproject.toml:
    # my-sdk-conformance = "my_sdk.conformance:main"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avp.agent.mock import ScriptedResolver
from avp.conformance.harness import (
    _ORDERING_FNS,
    CaseFailure,
    CaseResult,
    SkipCase,
    _check_final_state,
    _trajectory_to_dicts,
)
from avp.conformance.matcher import matches_partial
from avp.types import AgentDescriptor, Commission

CaseRunner = Callable[[dict[str, Any]], list[BaseModel]]


# ── Case-shape parsers (reusable across per-SDK harnesses) ────────────────────


def build_commission(case: dict[str, Any]) -> Commission:
    """`Commission.model_validate(case["commission"])` — separated as a
    helper so per-SDK harnesses don't repeat the import."""
    return Commission.model_validate(case["commission"])


def build_descriptor(case: dict[str, Any]) -> AgentDescriptor | None:
    """Build the `AgentDescriptor` for a case, merging the AVPAgent-shape
    `agent_builtin_tools` constructor-arg field into
    `descriptor.built_in_tools` when present. Synthesizes a minimal
    descriptor when the case ships builtins but no descriptor at all."""
    desc = dict(case.get("agent_descriptor") or {})
    builtins = case.get("agent_builtin_tools") or []
    if builtins:
        desc.setdefault("agent_name", "avp-conformance")
        desc.setdefault("agent_version", "0.0.0")
        desc.setdefault("avp_spec_version", "0.1")
        existing = list(desc.get("built_in_tools") or [])
        existing_names = {t.get("name") for t in existing}
        for entry in builtins:
            if entry.get("name") not in existing_names:
                existing.append(entry)
        desc["built_in_tools"] = existing
    return AgentDescriptor.model_validate(desc) if desc else None


def build_resolver(case: dict[str, Any], commission: Commission) -> ScriptedResolver | None:
    """Build the `ScriptedResolver` from `case["scripted_resolver"]`.
    Returns None when the commission carries no managed assets or the
    case sets `omit_resolver: true` (exercises the
    `resolver_not_configured` startup gate)."""
    has_managed = bool(commission.mcp_servers or commission.skills or commission.subagents)
    if not has_managed or case.get("omit_resolver"):
        return None
    sr = case.get("scripted_resolver") or {}
    return ScriptedResolver(
        resolutions=sr.get("resolutions") or {},
        subagent_spawns=sr.get("subagent_spawns") or {},
    )


# ── Case execution ────────────────────────────────────────────────────────────


def run_case(path: Path, runner: CaseRunner) -> CaseResult:
    """Load one case file, invoke `runner(case_dict)` to produce events,
    evaluate the case's expectations against the resulting trajectory,
    return a `CaseResult`."""
    case = json.loads(path.read_text())
    case_id = case.get("id") or path.stem
    failures: list[CaseFailure] = []
    traj: list[dict[str, Any]] = []

    t0 = time.monotonic()
    try:
        events = runner(case)
        traj = _trajectory_to_dicts(events)
    except SkipCase as skip:
        return CaseResult(
            case_id=case_id,
            path=path,
            passed=True,
            skipped=True,
            skip_reason=skip.reason,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:
        return CaseResult(
            case_id=case_id,
            path=path,
            passed=False,
            failures=[CaseFailure(label="runner-error", detail=f"{type(exc).__name__}: {exc}")],
            trajectory=traj,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    expectations = case.get("expectations") or {}
    matchers = expectations.get("events") or []
    ordering = expectations.get("ordering", "in_order_subsequence")
    fn = _ORDERING_FNS.get(ordering)
    if fn is None:
        failures.append(
            CaseFailure(label="harness-bug", detail=f"unknown ordering mode {ordering!r}")
        )
    elif matchers:
        ok, msg = fn(matchers, traj)
        if not ok:
            failures.append(CaseFailure(label=f"events ({ordering})", detail=msg))

    for fb in expectations.get("forbidden_events") or []:
        pattern = fb["match"]
        for ev in traj:
            if matches_partial(pattern, ev):
                label = fb.get("label") or "forbidden_events"
                failures.append(
                    CaseFailure(label=f"forbidden: {label}", detail=f"event matched: {ev}")
                )
                break

    if "final_state" in expectations:
        ok, msg = _check_final_state(expectations["final_state"], traj)
        if not ok:
            failures.append(CaseFailure(label="final_state", detail=msg))

    return CaseResult(
        case_id=case_id,
        path=path,
        passed=not failures,
        failures=failures,
        trajectory=traj,
        duration_ms=int((time.monotonic() - t0) * 1000),
    )


def run_suite(cases_dir: Path, runner: CaseRunner) -> list[CaseResult]:
    """Run every `*.json` case under `cases_dir` (recursive)."""
    return [run_case(p, runner) for p in sorted(cases_dir.rglob("*.json"))]


def _find_workspace_root(start: Path | None = None) -> Path | None:
    cur = (start or Path.cwd()).resolve()
    while True:
        if (cur / "conformance" / "v0.1").is_dir():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def make_translator_cli(
    *,
    translator_cls: Callable[..., Any],
    prog: str,
    description: str | None = None,
    skip_flags: dict[str, str] | None = None,
) -> Callable[[list[str] | None], int]:
    """Build a CLI for a per-SDK harness that wraps a translator with the
    canonical constructor signature.

    `translator_cls(commission=..., on_event=..., resolver=..., descriptor=...)`
    must be the call shape, with a `.run()` method that drives the SDK and
    invokes `on_event` for every emitted event.

    `skip_flags` maps case-dict keys to skip reasons; when any listed key is
    truthy in the case, the runner raises `SkipCase(reason)`. Use this for
    cases that require a deterministic-model harness (`scripted_only`) and
    therefore can't be exercised against a live LLM.
    """
    flags = skip_flags or {}

    def _run_one(case: dict[str, Any]) -> list[BaseModel]:
        for key, reason in flags.items():
            if case.get(key):
                raise SkipCase(reason)
        commission = build_commission(case)
        events: list[BaseModel] = []
        translator = translator_cls(
            commission=commission,
            on_event=events.append,
            resolver=build_resolver(case, commission),
            descriptor=build_descriptor(case),
        )
        translator.run()
        return events

    return make_cli(runner=_run_one, prog=prog, description=description)


def make_cli(
    *, runner: CaseRunner, prog: str, description: str | None = None
) -> Callable[[list[str] | None], int]:
    """Build a `main(argv) -> int` CLI for a per-SDK conformance harness.

    Same flag surface as `avp-conformance run`:

        <prog> run                          # all cases under conformance/v0.1/cases/
        <prog> run --case <path>            # one case
        <prog> run --suite <dir>            # custom suite directory
        <prog> run -v                       # dump trajectory tail on failure

    `conformance/v0.1/` is discovered by walking up from CWD.
    """

    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(
            prog=prog, description=description or f"{prog} — v0.1 conformance harness"
        )
        sub = parser.add_subparsers(dest="cmd", required=True)
        p_run = sub.add_parser("run", help="execute conformance cases")
        g = p_run.add_mutually_exclusive_group()
        g.add_argument("--case", type=Path, help="run a single case file")
        g.add_argument("--suite", type=Path, help="directory of *.json cases (recursive)")
        p_run.add_argument(
            "-v", "--verbose", action="store_true", help="dump trajectory on failure"
        )
        args = parser.parse_args(argv)

        if args.case:
            results = [run_case(args.case, runner)]
        else:
            suite = args.suite
            if suite is None:
                root = _find_workspace_root()
                if root is None:
                    print(
                        "error: could not find conformance/v0.1/ from CWD; pass --suite explicitly",
                        file=sys.stderr,
                    )
                    return 2
                suite = root / "conformance" / "v0.1" / "cases"
            results = run_suite(suite, runner)

        if not results:
            print(f"no cases found under {args.suite or args.case}", file=sys.stderr)
            return 2

        fails = 0
        skipped = 0
        for r in results:
            if r.skipped:
                skipped += 1
                reason = f" — {r.skip_reason}" if r.skip_reason else ""
                print(f"SKIP  {r.case_id}{reason}")
            elif r.passed:
                print(f"PASS  {r.case_id}  ({r.duration_ms}ms)")
            else:
                fails += 1
                print(f"FAIL  {r.case_id}  ({r.duration_ms}ms)")
                for f in r.failures:
                    print(f"        {f.label}: {f.detail}")
                if args.verbose:
                    print("      trajectory:")
                    for ev in r.trajectory[-30:]:
                        print(f"        {ev.get('source', '?'):>10}  {ev.get('type', '?')}")
        print()
        total = len(results)
        msg = f"{total - fails - skipped} / {total} cases passed"
        if skipped:
            msg += f" ({skipped} skipped)"
        print(msg)
        return 0 if fails == 0 else 1

    return main

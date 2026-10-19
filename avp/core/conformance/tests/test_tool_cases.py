"""Recorder -> the tool-call cases: a correct translator passes each, and the
translator bugs they exist for fail them.

Each trajectory is built through the shared Recorder exactly as an adapter
would report it, then mutated into the shape a known translator bug produces:
parallel results handed to each other's calls, a failure recorded as a
success, a call that never returns, a result reported twice.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from importlib.resources import files

from avp_conformance._match import match_case
from avp_conformance.case import TestCase as Case

from avp.content import TextBlock, ToolUseBlock
from avp.descriptor import AgentDescriptor, McpServerDecl, ToolDecl
from avp.recorder import Recorder
from avp.trajectory import StopReason


def _case(name: str) -> Case:
    return Case.model_validate_json(
        files("avp_conformance").joinpath(f"cases/v0.1/mcp/{name}.json").read_text()
    )


def _record(case: Case, script) -> list[dict]:
    """Drive the Recorder through `script(rec)` between the prelude and stop."""
    events: list[dict] = []

    async def sink(event):
        events.append(event.model_dump(by_alias=True, exclude_none=True))

    async def drive():
        rec = Recorder(sink)
        await rec.prelude(
            case.commission,
            AgentDescriptor(agent_name="framework", agent_version="1", spec_version="0.1"),
        )
        await rec.start(
            tools=[
                ToolDecl(name=n, mcp_server_id="avptest")
                for n in ("Avptest_Echo", "Avptest_Add", "Avptest_Fail")
            ],
            mcp_servers=[McpServerDecl(id="avptest", status="connected")],
        )
        await script(rec)
        await rec.stop(StopReason.converged)

    asyncio.run(drive())
    return events


def _use(call: str, name: str, **args) -> ToolUseBlock:
    return ToolUseBlock(id=call, name=name, input=args)


def _returned(events: list[dict], call: str) -> dict:
    return next(
        e["data"]
        for e in events
        if e["type"] == "avp.tool_returned" and e["data"]["avp.tool.call_id"] == call
    )


def _fails(events: list[dict], case: Case, *needles: str) -> None:
    result = match_case(events, case.expectations)
    assert not result.ok
    for needle in needles:
        assert any(needle in r for r in result.reasons), result.reasons


def test_parallel_calls_pass_and_swapped_results_fail():
    case = _case("parallel-tool-calls")

    async def script(rec):
        await rec.assistant(
            [
                _use("a", "Avptest_Echo", text="AVP-PAR-ALPHA"),
                _use("b", "Avptest_Echo", text="AVP-PAR-BETA"),
            ]
        )
        # Results arrive out of order; each still pairs by its own id.
        await rec.tool_result("b", "AVP-PAR-BETA")
        await rec.tool_result("a", "AVP-PAR-ALPHA")
        await rec.assistant([TextBlock(text="AVP-PAR-ALPHA AVP-PAR-BETA")])

    events = _record(case, script)
    assert match_case(events, case.expectations).ok

    # Paired by position: each call carries the other's result. Ids stay
    # consistent, so only the per-call expectation sees it.
    swapped = deepcopy(events)
    a, b = _returned(swapped, "a"), _returned(swapped, "b")
    a["avp.tool_result"]["content"], b["avp.tool_result"]["content"] = (
        b["avp.tool_result"]["content"],
        a["avp.tool_result"]["content"],
    )
    _fails(swapped, case, "tool_calls: no call matched")

    # One result reported under the other call's id.
    misfiled = deepcopy(events)
    _returned(misfiled, "a")["avp.tool_result"]["tool_use_id"] = "b"
    _fails(misfiled, case, "carries the result for 'b'")

    # A batch reported once: the second call never returns.
    dropped = [
        e
        for e in events
        if not (e["type"] == "avp.tool_returned" and e["data"]["avp.tool.call_id"] == "b")
    ]
    _fails(dropped, case, "call 'b' never returned in a converged run")


def test_a_call_returned_twice_fails():
    case = _case("parallel-tool-calls")

    async def script(rec):
        await rec.assistant(
            [
                _use("a", "Avptest_Echo", text="AVP-PAR-ALPHA"),
                _use("b", "Avptest_Echo", text="AVP-PAR-BETA"),
            ]
        )
        await rec.tool_result("a", "AVP-PAR-ALPHA")
        await rec.tool_result("b", "AVP-PAR-BETA")
        await rec.assistant([TextBlock(text="AVP-PAR-ALPHA AVP-PAR-BETA")])

    events = _record(case, script)
    twice = deepcopy(events)
    i = next(i for i, e in enumerate(twice) if e["type"] == "avp.tool_returned")
    twice.insert(i + 1, deepcopy(twice[i]))
    _fails(twice, case, "returned more than once")


def test_multi_round_calls_pass_and_a_misattributed_result_fails():
    case = _case("multi-round-tool-calls")

    async def script(rec):
        await rec.assistant([_use("r1", "Avptest_Add", a=17, b=25)])
        await rec.tool_result("r1", "42")
        await rec.assistant([_use("r2", "Avptest_Add", a=42, b=8)])
        await rec.tool_result("r2", "50")
        await rec.assistant([_use("r3", "Avptest_Echo", text="AVP-SUM-50")])
        await rec.tool_result("r3", "AVP-SUM-50")
        await rec.assistant([TextBlock(text="AVP-SUM-50")])

    events = _record(case, script)
    assert match_case(events, case.expectations).ok
    assert sum(e["type"] == "avp.assistant_message" for e in events) == 4

    # A late result filed under the next round's call.
    late = deepcopy(events)
    _returned(late, "r1")["avp.tool_result"]["content"] = "50"
    _returned(late, "r2")["avp.tool_result"]["content"] = "42"
    _fails(late, case, "tool_calls: no call matched")


def test_failing_calls_pass_only_when_recorded_as_errors():
    for name, marker, mode in [
        ("tool-error-result-is-recorded", "AVP-FAIL-RESULT", "result"),
        ("tool-protocol-error-is-recorded", "AVP-FAIL-PROTOCOL", "protocol"),
    ]:
        case = _case(name)

        async def script(rec, marker=marker, mode=mode):
            await rec.assistant([_use("f", "Avptest_Fail", message=marker, mode=mode)])
            await rec.tool_result("f", f"MCP error -32000: {marker}", is_error=True)
            await rec.assistant([TextBlock(text=f"The tool failed: {marker}")])

        events = _record(case, script)
        assert match_case(events, case.expectations).ok, name

        # The failure text kept but the flag dropped: a failed action on the
        # wire as a success.
        as_success = deepcopy(events)
        _returned(as_success, "f")["avp.tool_result"]["is_error"] = False
        _fails(as_success, case, "tool_calls: no call matched")


def test_a_tool_use_without_tool_invoked_fails():
    case = _case("multi-round-tool-calls")

    async def script(rec):
        await rec.assistant([_use("r1", "Avptest_Add", a=17, b=25)])
        await rec.tool_result("r1", "42")
        await rec.assistant([TextBlock(text="done")])

    events = _record(case, script)
    no_dispatch = [e for e in events if e["type"] not in {"avp.tool_invoked", "avp.tool_returned"}]
    _fails(no_dispatch, case, "tool_use 'r1' has no tool_invoked")


def test_an_interrupted_run_may_stop_with_a_call_in_flight():
    case = _case("multi-round-tool-calls")
    events: list[dict] = []

    async def sink(event):
        events.append(event.model_dump(by_alias=True, exclude_none=True))

    async def drive():
        rec = Recorder(sink)
        await rec.prelude(
            case.commission,
            AgentDescriptor(agent_name="framework", agent_version="1", spec_version="0.1"),
        )
        await rec.start()
        await rec.assistant([_use("r1", "Avptest_Add", a=17, b=25)])
        await rec.stop(StopReason.interrupted)

    asyncio.run(drive())
    reasons = match_case(events, case.expectations).reasons
    assert not any(r.startswith("tools:") for r in reasons), reasons

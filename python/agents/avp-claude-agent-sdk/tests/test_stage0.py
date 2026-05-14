"""Stage 0 smoke tests: patches are idempotent; runstate context-var is correctly scoped."""

from __future__ import annotations

import asyncio

import claude_agent_sdk

from avp_claude_agent_sdk._patches import _AVP_WRAPPED, _restore_patches, setup_avp
from avp_claude_agent_sdk._runstate import RunState, current_run, reset_run, set_run

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop_sink(event: object) -> object:  # sync noop — fine for state construction
    return None


def _make_state(run_id: str = "run-0", trace_id_char: str = "a") -> RunState:
    return RunState(trace_id=trace_id_char * 32, run_id=run_id, sink=_noop_sink)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Patch tests
# ---------------------------------------------------------------------------


class TestPatches:
    def setup_method(self) -> None:
        _restore_patches()

    def teardown_method(self) -> None:
        _restore_patches()

    def test_apply_replaces_query(self) -> None:
        original = claude_agent_sdk.query
        setup_avp()
        assert claude_agent_sdk.query is not original
        assert getattr(claude_agent_sdk.query, _AVP_WRAPPED, False)

    def test_apply_is_idempotent(self) -> None:
        setup_avp()
        wrapped_first = claude_agent_sdk.query
        setup_avp()
        assert claude_agent_sdk.query is wrapped_first

    def test_restore_undoes_apply(self) -> None:
        original = claude_agent_sdk.query
        setup_avp()
        _restore_patches()
        assert claude_agent_sdk.query is original

    def test_restore_is_idempotent(self) -> None:
        setup_avp()
        _restore_patches()
        _restore_patches()  # must not raise


# ---------------------------------------------------------------------------
# RunState context-var tests
# ---------------------------------------------------------------------------


class TestRunStateContextVar:
    def test_default_is_none(self) -> None:
        assert current_run() is None

    def test_set_and_reset(self) -> None:
        state = _make_state()
        token = set_run(state)
        try:
            assert current_run() is state
        finally:
            reset_run(token)
        assert current_run() is None

    def test_nested_scopes_restore_outer(self) -> None:
        outer = _make_state("outer")
        inner = _make_state("inner", "b")
        t1 = set_run(outer)
        t2 = set_run(inner)
        assert current_run() is inner
        reset_run(t2)
        assert current_run() is outer
        reset_run(t1)
        assert current_run() is None

    def test_context_var_isolated_per_asyncio_task(self) -> None:
        """Two concurrent tasks see their own RunState without interference."""
        seen: list[str | None] = []

        async def task(state: RunState) -> None:
            token = set_run(state)
            await asyncio.sleep(0)  # yield control so tasks interleave
            seen.append(current_run().run_id if current_run() else None)
            reset_run(token)

        async def run() -> None:
            s1, s2 = _make_state("run-1"), _make_state("run-2", "b")
            await asyncio.gather(task(s1), task(s2))

        asyncio.run(run())
        assert set(seen) == {"run-1", "run-2"}

"""Tests for AnthropicTracedClient + wrap_anthropic — drop-in AVP
instrumentation over an existing Anthropic SDK loop.

User code looks like a vanilla Anthropic loop:

    with AnthropicTracedClient(real, commission=cfg, on_event=publish) as client:
        while True:
            resp = client.messages.create(...)
            if resp.stop_reason == "end_turn":
                client.converged()
                break
            ...

These tests pin the contract:

  - Lifecycle: run_requested + agent_started on `__enter__`,
    agent_stopped on `__exit__`.
  - One `messages.create()` call → one `assistant_message`, before yield.
  - Token / cost extraction is byte-identical to `AnthropicModelDriver`
    (both go through the same Anthropic→ModelResponse walker).
  - The wrapper returns the underlying Message UNMODIFIED.
  - `client.tool(...)` / `client.subagent(...)` emit the paired events.
  - `wrap_anthropic` proxies emit to the active run via the ContextVar.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from avp.commission import Commission
from avp.content import TextBlock
from avp.trajectory import (
    AgentStartedEvent,
    AgentStoppedEvent,
    AssistantMessageEvent,
    StopReason,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from avp_anthropic import AnthropicModelDriver, AnthropicTracedClient, wrap_anthropic


class _FakeMessages:
    """Stand-in for `anthropic.Anthropic().messages`. Returns scripted
    responses one at a time and captures calls."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("test asked for more turns than scripted")
        return self._responses.pop(0)


class _FakeAnthropic:
    """Stand-in for `anthropic.Anthropic()`. Exposes `.messages` and a `.beta`
    attribute to verify __getattr__ pass-through."""

    def __init__(self, responses: list[Any]) -> None:
        self.messages = _FakeMessages(responses)
        self.beta = SimpleNamespace(some_resource="here")


def _resp(
    *,
    text: str | None = None,
    tool_use: dict | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 50,
    output_tokens: int = 10,
    cache_read: int = 0,
    cache_write: int = 0,
    model: str = "claude-sonnet-4-6",
) -> SimpleNamespace:
    blocks: list[Any] = []
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))
    if tool_use:
        blocks.append(SimpleNamespace(type="tool_use", **tool_use))
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
        stop_reason=stop_reason,
        model=model,
    )


def _basic_config(**overrides) -> Commission:
    base: dict = {
        "schema_version": "0.1",
        "run_id": "traced-client-test",
        "model": "claude-sonnet-4-6",
        "prompt": "hi",
    }
    base.update(overrides)
    return Commission(**base)


def _by_type(events: list, type_: type) -> list:
    return [e for e in events if isinstance(e, type_)]


def _types(events: list) -> list[str]:
    return [type(e).__name__ for e in events]


def _text_of(msg: AssistantMessageEvent) -> str | None:
    for block in msg.data.content:
        if isinstance(block, TextBlock):
            return block.text
    return None


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_enter_exit_emit_full_lifecycle_around_a_single_create_call() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="hello", input_tokens=40, output_tokens=8)])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        resp = client.messages.create(model="claude-sonnet-4-6", messages=[])
        assert resp.stop_reason == "end_turn"
        client.converged()

    types = _types(out)
    assert types[0] == "RunRequestedEvent"
    assert "AgentStartedEvent" in types
    assert types[-1] == "AgentStoppedEvent"
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert stopped.data.reason == StopReason.converged


def test_create_call_emits_one_assistant_message_carrying_text() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="hello", input_tokens=40, output_tokens=8)])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()

    msgs = _by_type(out, AssistantMessageEvent)
    assert len(msgs) == 1
    assert _text_of(msgs[0]) == "hello"


def test_messages_returns_underlying_anthropic_message_unmodified() -> None:
    out: list = []
    msg = _resp(text="preserved", stop_reason="end_turn")
    fake = _FakeAnthropic([msg])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        resp = client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    assert resp is msg
    assert resp.stop_reason == "end_turn"
    assert resp.content[0].text == "preserved"


# ── Token / cost extraction (parity with the driver) ─────────────────────────


def test_token_and_cost_extraction_match_anthropic_model_driver() -> None:
    """The translator ↔ SDK seam: the traced client and AnthropicModelDriver
    MUST produce byte-identical tokens/cost for the same response (they share
    the Anthropic→ModelResponse walker). A 30%-undercount bug hid here once."""
    resp = _resp(text="x", input_tokens=100, output_tokens=20, cache_read=30, cache_write=10)

    out: list = []
    fake = _FakeAnthropic([resp])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    msg = _by_type(out, AssistantMessageEvent)[0]

    # Same response straight through the driver.
    class _One:
        def __init__(self, r):
            self._r = r
            self.messages = self

        def create(self, **_):
            return self._r

    mr = AnthropicModelDriver(model="claude-sonnet-4-6", client=_One(resp)).step(
        [{"role": "user", "content": "x"}]
    )

    # 100 fresh + 30 cache_read + 10 cache_write = 140 (AVP convention).
    assert msg.data.usage.input_tokens == 140 == mr.tokens_input
    assert msg.data.usage.output_tokens == 20 == mr.tokens_output
    assert msg.data.usage.cache_read_input_tokens == 30
    assert msg.data.usage.cache_creation_input_tokens == 10
    assert msg.data.cost_usd == mr.cost_usd
    assert msg.data.cost_usd > 0


def test_cost_zero_for_unknown_model() -> None:
    import warnings

    out: list = []
    fake = _FakeAnthropic([_resp(text="x", model="some-unknown-model")])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with AnthropicTracedClient(
            fake, commission=_basic_config(model="some-unknown-model"), on_event=out.append
        ) as client:
            client.messages.create(model="some-unknown-model", messages=[])
            client.converged()
    msg = _by_type(out, AssistantMessageEvent)[0]
    assert msg.data.cost_usd == 0.0


def test_wrapper_records_finish_reason_from_stop_reason() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x", stop_reason="tool_use")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    msg = _by_type(out, AssistantMessageEvent)[0]
    assert msg.data.response_finish_reasons == ["tool_use"]


def test_two_calls_produce_two_turns_with_distinct_span_ids_and_steps() -> None:
    out: list = []
    fake = _FakeAnthropic(
        [
            _resp(text="first", stop_reason="tool_use", input_tokens=30, output_tokens=10),
            _resp(text="second", stop_reason="end_turn", input_tokens=40, output_tokens=15),
        ]
    )
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    msgs = _by_type(out, AssistantMessageEvent)
    assert len(msgs) == 2
    assert msgs[0].data.span_id != msgs[1].data.span_id
    assert msgs[0].data.step == 1 and msgs[1].data.step == 2


# ── Tool / subagent context managers ─────────────────────────────────────────


def test_tool_context_manager_emits_tool_invoked_and_returned() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        with client.tool(call_id="c1", name="bash", input={"command": "ls"}) as t:
            t.record("file1\nfile2")
        client.converged()
    inv = _by_type(out, ToolInvokedEvent)[0]
    ret = _by_type(out, ToolReturnedEvent)[0]
    assert inv.data.tool_name == "bash"
    assert ret.data.tool_result.content == "file1\nfile2"
    # tool_returned parents under the tool_invoked span (paired frame).
    assert ret.data.parent_span_id == inv.data.span_id


def test_tool_failure_marks_result_error() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        with client.tool(call_id="c1", name="bash", input={}) as t:
            t.fail("boom")
        client.converged()
    ret = _by_type(out, ToolReturnedEvent)[0]
    assert ret.data.tool_result.is_error is True
    assert ret.data.tool_result.content == "boom"


def test_subagent_context_manager_emits_invoked_and_returned() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        with client.subagent(name="researcher", input={"prompt": "go"}) as sa:
            sa.record_result("found 1")
        client.converged()
    inv = _by_type(out, SubagentInvokedEvent)[0]
    ret = _by_type(out, SubagentReturnedEvent)[0]
    assert inv.data.subagent_name == "researcher"
    assert inv.data.span_id == ret.data.span_id  # same frame
    assert ret.data.subagent_result_text == "found 1"
    assert ret.data.subagent_reason == StopReason.converged


def test_subagent_fail_marks_error_reason() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        with client.subagent(name="researcher") as sa:
            sa.fail("crashed")
        client.converged()
    ret = _by_type(out, SubagentReturnedEvent)[0]
    assert ret.data.subagent_reason == StopReason.error
    assert ret.data.subagent_result_text == "crashed"


# ── Pass-through + lifecycle guards ──────────────────────────────────────────


def test_attribute_passthrough_to_underlying_client() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        assert client.beta.some_resource == "here"
        assert client.real is fake
        client.converged()


def test_messages_access_before_enter_raises() -> None:
    fake = _FakeAnthropic([])
    client = AnthropicTracedClient(fake, commission=_basic_config(), on_event=lambda _: None)
    with pytest.raises(RuntimeError, match="must be used as `with`"):
        _ = client.messages


def test_reused_client_raises() -> None:
    fake = _FakeAnthropic([_resp(text="x")])
    client = AnthropicTracedClient(fake, commission=_basic_config(), on_event=lambda _: None)
    with client:
        pass
    with pytest.raises(RuntimeError, match="cannot be reused"):
        with client:
            pass


def test_exception_in_block_stops_with_error() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with pytest.raises(ValueError, match="boom"):
        with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
            client.messages.create(model="claude-sonnet-4-6", messages=[])
            raise ValueError("boom")
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert stopped.data.reason == StopReason.error


# ── agent_started carries the run config ─────────────────────────────────────


def test_agent_started_carries_prompt_and_model() -> None:
    out: list = []
    fake = _FakeAnthropic([])
    with AnthropicTracedClient(
        fake, commission=_basic_config(prompt="do the thing"), on_event=out.append
    ):
        pass
    started = _by_type(out, AgentStartedEvent)[0]
    assert started.data.prompt == "do the thing"
    assert started.data.request_model == "claude-sonnet-4-6"
    assert started.data.provider_name == "anthropic"


# ── Beta surface ─────────────────────────────────────────────────────────────


class _FakeBeta:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = _FakeMessages(responses)


class _FakeAnthropicWithBeta(_FakeAnthropic):
    def __init__(
        self,
        responses: list[Any] | None = None,
        beta_responses: list[Any] | None = None,
    ) -> None:
        super().__init__(responses or [])
        self.beta = _FakeBeta(beta_responses or [])


def test_beta_messages_create_is_instrumented() -> None:
    out: list = []
    fake = _FakeAnthropicWithBeta(beta_responses=[_resp(text="from beta")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        resp = client.beta.messages.create(model="claude-sonnet-4-6", messages=[])
        assert resp.content[0].text == "from beta"
        client.converged()
    msgs = _by_type(out, AssistantMessageEvent)
    assert len(msgs) == 1
    assert _text_of(msgs[0]) == "from beta"


# ── wrap_anthropic factory (active-run mode) ─────────────────────────────────


def test_wrap_anthropic_is_idempotent() -> None:
    fake = _FakeAnthropic([])
    wrapped = wrap_anthropic(fake)
    assert wrap_anthropic(wrapped) is wrapped


def test_wrap_anthropic_unknown_client_type_returns_unchanged() -> None:
    class SomeOtherClient:
        pass

    obj = SomeOtherClient()
    assert wrap_anthropic(obj) is obj


def test_wrap_anthropic_raises_outside_active_run() -> None:
    fake = _FakeAnthropic([_resp(text="x")])
    client = wrap_anthropic(fake)
    with pytest.raises(RuntimeError, match="No active traced run"):
        client.messages.create(model="claude-sonnet-4-6", messages=[])


def test_wrap_anthropic_emits_to_active_run() -> None:
    """A standalone `wrap_anthropic` proxy finds the active run set by an
    enclosing `AnthropicTracedClient` and emits its turns there."""
    out: list = []
    fake = _FakeAnthropic([_resp(text="hello")])
    proxy = wrap_anthropic(fake)
    with AnthropicTracedClient(_FakeAnthropic([]), commission=_basic_config(), on_event=out.append):
        resp = proxy.messages.create(model="claude-sonnet-4-6", messages=[])
        assert resp.content[0].text == "hello"
    assert _by_type(out, AssistantMessageEvent)


def test_wrap_anthropic_handles_async_client() -> None:
    import asyncio

    class _FakeAsyncMessages:
        def __init__(self, responses: list[Any]) -> None:
            self._responses = list(responses)

        async def create(self, **kwargs: Any) -> Any:
            return self._responses.pop(0)

    class _FakeAsyncAnthropic:
        def __init__(self, responses: list[Any]) -> None:
            self.messages = _FakeAsyncMessages(responses)

    fake = _FakeAsyncAnthropic([_resp(text="async hello")])
    fake.__class__.__name__ = "AsyncAnthropic"
    proxy = wrap_anthropic(fake)

    out: list = []

    async def _run() -> None:
        with AnthropicTracedClient(
            _FakeAnthropic([]), commission=_basic_config(), on_event=out.append
        ):
            resp = await proxy.messages.create(model="claude-sonnet-4-6", messages=[])
            assert resp.content[0].text == "async hello"

    asyncio.run(_run())
    msgs = _by_type(out, AssistantMessageEvent)
    assert msgs and _text_of(msgs[0]) == "async hello"

"""Unit tests for `setup_avp` -- the module-level monkeypatch that
swaps `claude_agent_sdk.ClaudeSDKClient` for an AVP-instrumented
subclass. Covers idempotency, sink injection / re-configuration, and
`sys.modules` rebind for callers that imported the symbol before patch.
"""

from __future__ import annotations

import claude_agent_sdk
import pytest

from avp.agent.sink import stdio_sink
from avp.trajectory import Event
from avp_claude_agent_sdk import AVPClaudeSDKClient, setup_avp
from avp_claude_agent_sdk._patches import _AVP_WRAPPED, _restore_patches


@pytest.fixture(autouse=True)
def _restore() -> None:
    """Make sure each test starts from an unpatched module and cleans up."""
    _restore_patches()
    yield
    _restore_patches()


def test_setup_avp_swaps_class_with_marker() -> None:
    original = claude_agent_sdk.ClaudeSDKClient
    assert not getattr(original, _AVP_WRAPPED, False)

    setup_avp()

    patched = claude_agent_sdk.ClaudeSDKClient
    assert patched is not original
    assert getattr(patched, _AVP_WRAPPED, False)
    assert issubclass(patched, AVPClaudeSDKClient)


def test_setup_avp_is_idempotent() -> None:
    setup_avp()
    first = claude_agent_sdk.ClaudeSDKClient
    setup_avp()
    second = claude_agent_sdk.ClaudeSDKClient
    assert first is second


def test_setup_avp_updates_sink_on_second_call() -> None:
    """Second call with a new sink updates the sink for future
    instances without re-patching the class."""
    events_a: list[Event] = []
    events_b: list[Event] = []

    async def sink_a(event: Event) -> None:
        events_a.append(event)

    async def sink_b(event: Event) -> None:
        events_b.append(event)

    setup_avp(sink=sink_a)
    patched = claude_agent_sdk.ClaudeSDKClient
    inst_a = patched()
    assert inst_a._sink is sink_a

    setup_avp(sink=sink_b)
    # Class identity preserved (no re-patch).
    assert claude_agent_sdk.ClaudeSDKClient is patched
    inst_b = patched()
    assert inst_b._sink is sink_b
    # Previously-constructed instance retains its own sink.
    assert inst_a._sink is sink_a


def test_setup_avp_default_sink_is_stdio() -> None:
    setup_avp()
    inst = claude_agent_sdk.ClaudeSDKClient()
    assert inst._sink is stdio_sink


def test_setup_avp_rebinds_sys_modules_references() -> None:
    """A module that did `from claude_agent_sdk import ClaudeSDKClient`
    before `setup_avp()` ran MUST end up with the wrapper class on its
    own namespace, mirroring `ClassReplacementPatcher` semantics. The
    `claude_agent_sdk.client` submodule is a convenient live `sys.modules`
    entry that holds such a binding without inventing a fake module."""
    from claude_agent_sdk import client as client_submodule

    original = client_submodule.ClaudeSDKClient
    assert claude_agent_sdk.ClaudeSDKClient is original

    setup_avp()

    patched = claude_agent_sdk.ClaudeSDKClient
    assert patched is not original
    # The submodule's binding was rebound by the sys.modules sweep.
    assert client_submodule.ClaudeSDKClient is patched


def test_sweep_skips_avp_claude_agent_sdk_package() -> None:
    """The sweep MUST NOT rebind `ClaudeSDKClient` inside our own
    package: `_client._probe_describe` deliberately instantiates the
    upstream class to do a probe pass during `connect()`. If the sweep
    rebound that reference to the wrapper, the probe would recursively
    invoke the wrapper's connect → infinite recursion (the hang seen
    when running `scripts/run_query.py`)."""
    from avp_claude_agent_sdk import _client as wrapper_client_module

    original = claude_agent_sdk.ClaudeSDKClient
    assert wrapper_client_module.ClaudeSDKClient is original

    setup_avp()

    assert claude_agent_sdk.ClaudeSDKClient is not original
    # The probe path's reference is preserved.
    assert wrapper_client_module.ClaudeSDKClient is original


def test_restore_patches_undoes_swap() -> None:
    original = claude_agent_sdk.ClaudeSDKClient
    setup_avp()
    assert claude_agent_sdk.ClaudeSDKClient is not original

    _restore_patches()
    assert claude_agent_sdk.ClaudeSDKClient is original
    # Idempotent: second restore is a no-op.
    _restore_patches()
    assert claude_agent_sdk.ClaudeSDKClient is original


def test_patched_class_accepts_explicit_sink_override() -> None:
    """Per-instance `sink=` kwarg wins over the configured default."""
    default_events: list[Event] = []
    override_events: list[Event] = []

    async def default_sink(event: Event) -> None:
        default_events.append(event)

    async def override_sink(event: Event) -> None:
        override_events.append(event)

    setup_avp(sink=default_sink)
    inst = claude_agent_sdk.ClaudeSDKClient(sink=override_sink)
    assert inst._sink is override_sink



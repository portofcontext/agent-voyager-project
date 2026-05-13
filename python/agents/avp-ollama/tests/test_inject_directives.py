"""Parser tests for the warm-rescue test-instrumentation env vars
(`OLLAMA_INJECT_USER_MESSAGE_AT`, `OLLAMA_INJECT_TOOL_CALL_AT`)."""

from __future__ import annotations

from avp_ollama.translator import InjectUserMessageAt, InjectToolCallAt


# ── OLLAMA_INJECT_USER_MESSAGE_AT ─────────────────────────────────────────


def test_user_msg_unset_means_no_fire():
    d = InjectUserMessageAt.from_env(None)
    assert d.turn == 0
    assert not d.should_fire_after_turn(1)
    assert not d.should_fire_after_turn(5)


def test_user_msg_turn_and_content_round_trip():
    d = InjectUserMessageAt.from_env("turn:2:KEY-4242")
    assert d.turn == 2
    assert d.content == "KEY-4242"
    assert not d.should_fire_after_turn(1)
    assert d.should_fire_after_turn(2)
    assert not d.should_fire_after_turn(3)


def test_user_msg_content_may_contain_colons():
    d = InjectUserMessageAt.from_env("turn:3:url is https://example.com/x:y")
    assert d.turn == 3
    assert d.content == "url is https://example.com/x:y"


def test_user_msg_invalid_inputs_disable_injection():
    for raw in ("garbage", "turn:not-a-number:hi", "turn:1:", "turn:0:something"):
        d = InjectUserMessageAt.from_env(raw)
        assert d.turn == 0, raw


# ── OLLAMA_INJECT_TOOL_CALL_AT ────────────────────────────────────────────


def test_tool_call_unset_means_no_fire():
    d = InjectToolCallAt.from_env(None)
    assert d.turn == 0
    assert not d.should_fire_before_turn(1)


def test_tool_call_round_trips():
    d = InjectToolCallAt.from_env('turn:1:echo:{"v":42}')
    assert d.turn == 1
    assert d.tool_name == "echo"
    assert d.args == {"v": 42}
    assert d.should_fire_before_turn(1)
    assert not d.should_fire_before_turn(2)


def test_tool_call_bad_json_disables():
    d = InjectToolCallAt.from_env("turn:1:echo:{not json}")
    assert d.turn == 0


def test_tool_call_missing_args_disables():
    d = InjectToolCallAt.from_env("turn:1:echo")
    assert d.turn == 0


def test_tool_call_bad_turn_number_disables():
    d = InjectToolCallAt.from_env('turn:zero:echo:{"v":1}')
    assert d.turn == 0


def test_tool_call_args_can_be_string_or_array():
    d = InjectToolCallAt.from_env('turn:2:echo:"hello"')
    assert d.args == "hello"
    d = InjectToolCallAt.from_env('turn:2:echo:[1,2,3]')
    assert d.args == [1, 2, 3]

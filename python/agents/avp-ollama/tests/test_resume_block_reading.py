"""Translator-side `Commission.resume` reading.

We don't drive the full `run()` loop here (it'd require a live Ollama
+ supervisor). Instead we cover the discrete behaviors:
  * `_extract_resume_block` extraction from Commission
  * `_resume_messages` parsing into chat shape
  * `_resume_tool_cache` parsing
  * `_seed_messages` chooses resume.context over Commission.prompt
  * `_lookup_tool_cache` finds matching entries by name + args"""

from __future__ import annotations

from unittest import mock

from avp_ollama.translator import OllamaTranslator, _extract_resume_block


COMMISSION_BASE = {
    "schema_version": "0.1",
    "run_id": "r-test",
    "model": "llama3.2:3b",
    "system_prompt": "be helpful",
    "prompt": "plan a trip",
}


def _make_translator(config: dict) -> OllamaTranslator:
    # Bypass the real SupervisorEventClient (no network).
    fake_client = mock.MagicMock()
    return OllamaTranslator(run_id="r-test", config=config, client=fake_client)


def test_extract_returns_none_when_resume_absent():
    cfg = dict(COMMISSION_BASE)
    assert _extract_resume_block(cfg) is None


def test_extract_returns_dict_when_resume_present():
    cfg = dict(COMMISSION_BASE)
    cfg["resume"] = {"from_seq": 5, "context": {"messages": []}, "tool_cache": []}
    assert _extract_resume_block(cfg) == cfg["resume"]


def test_extract_returns_none_when_resume_is_non_dict():
    cfg = dict(COMMISSION_BASE)
    cfg["resume"] = "not a dict"
    assert _extract_resume_block(cfg) is None


def test_resume_messages_round_trips():
    cfg = dict(COMMISSION_BASE)
    cfg["resume"] = {
        "from_seq": 7,
        "context": {
            "messages": [
                {"role": "system", "content": "be helpful"},
                {"role": "user", "content": "plan a trip"},
                {"role": "assistant", "content": "Day 1: Tokyo."},
            ]
        },
        "tool_cache": [],
    }
    t = _make_translator(cfg)
    msgs = t._resume_messages()
    assert len(msgs) == 3
    assert msgs[0] == {"role": "system", "content": "be helpful"}
    assert msgs[2]["role"] == "assistant"


def test_resume_messages_filters_malformed_entries():
    cfg = dict(COMMISSION_BASE)
    cfg["resume"] = {
        "from_seq": 0,
        "context": {
            "messages": [
                {"role": "user", "content": "ok"},
                "not a dict",
                {"role": 42, "content": "bad role type"},
                {"role": "user"},  # missing content
                {"role": "assistant", "content": "kept"},
            ]
        },
    }
    t = _make_translator(cfg)
    msgs = t._resume_messages()
    assert len(msgs) == 2
    assert msgs[0]["content"] == "ok"
    assert msgs[1]["content"] == "kept"


def test_seed_messages_prefers_resume_context_over_commission_prompt():
    cfg = dict(COMMISSION_BASE)
    cfg["resume"] = {
        "from_seq": 7,
        "context": {
            "messages": [
                {"role": "user", "content": "the rescued conversation"},
                {"role": "assistant", "content": "with full history"},
            ]
        },
    }
    t = _make_translator(cfg)
    seeded = t._seed_messages()
    # Should be the resume.context.messages — NOT the Commission's
    # system_prompt + prompt seeded by _initial_messages().
    assert len(seeded) == 2
    assert seeded[0]["content"] == "the rescued conversation"
    assert "be helpful" not in [m["content"] for m in seeded]


def test_seed_messages_falls_back_to_initial_when_resume_absent():
    cfg = dict(COMMISSION_BASE)
    t = _make_translator(cfg)
    seeded = t._seed_messages()
    # No resume → initial = system_prompt + prompt
    assert seeded[0] == {"role": "system", "content": "be helpful"}
    assert seeded[1] == {"role": "user", "content": "plan a trip"}


def test_seed_messages_falls_back_when_resume_messages_empty():
    cfg = dict(COMMISSION_BASE)
    cfg["resume"] = {"from_seq": 0, "context": {"messages": []}}
    t = _make_translator(cfg)
    seeded = t._seed_messages()
    assert seeded[0]["role"] == "system"


def test_tool_cache_lookup_matches_by_name_and_args():
    cfg = dict(COMMISSION_BASE)
    cfg["resume"] = {
        "from_seq": 0,
        "tool_cache": [
            {
                "tool_name": "echo",
                "args": {"v": "KEY-4242"},
                "result": {"v": "KEY-4242"},
                "tier": "idempotent",
                "original_span_id": "x",
            }
        ],
    }
    t = _make_translator(cfg)
    assert t._lookup_tool_cache("echo", {"v": "KEY-4242"}) is not None
    # Wrong tool name → miss
    assert t._lookup_tool_cache("other", {"v": "KEY-4242"}) is None
    # Wrong args → miss
    assert t._lookup_tool_cache("echo", {"v": "KEY-9999"}) is None
    # Missing cache → miss
    assert t._lookup_tool_cache("anything", None) is None


def test_tool_cache_empty_when_no_resume():
    cfg = dict(COMMISSION_BASE)
    t = _make_translator(cfg)
    assert t._resume_tool_cache() == []


def test_execute_stub_tool_echo_returns_args_verbatim():
    cfg = dict(COMMISSION_BASE)
    t = _make_translator(cfg)
    assert t._execute_stub_tool("echo", {"v": 1}) == {"v": 1}
    assert t._execute_stub_tool("echo", "hello") == "hello"


def test_execute_stub_tool_unknown_returns_synthetic():
    cfg = dict(COMMISSION_BASE)
    t = _make_translator(cfg)
    result = t._execute_stub_tool("unknown_tool", {"x": 1})
    assert result == {"_stub": True, "tool_name": "unknown_tool", "args": {"x": 1}}

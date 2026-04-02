"""Tests for AepConfig parsing and serialization."""

import pytest
from agent_execution_protocol import AepConfig
from agent_execution_protocol.config import AepBoundary, AepHook


# ── AepBoundary ───────────────────────────────────────────────────────────────

def test_boundary_omits_none_fields():
    b = AepBoundary(max_steps=10)
    d = b.to_dict()
    assert "max_steps" in d
    assert "max_cost_usd" not in d
    assert "max_tokens" not in d


def test_boundary_all_fields():
    b = AepBoundary(max_cost_usd=2.0, max_steps=20, max_tokens=50000)
    d = b.to_dict()
    assert d == {"max_cost_usd": 2.0, "max_steps": 20, "max_tokens": 50000}


def test_boundary_round_trip():
    d = {"run_id": "r1", "model": "m", "boundary": {"max_cost_usd": 2.0, "max_steps": 20}}
    cfg = AepConfig.from_dict(AepConfig.from_dict(d).to_dict())
    assert cfg.boundary.max_cost_usd == 2.0
    assert cfg.boundary.max_steps == 20
    assert cfg.boundary.max_tokens is None


def test_boundary_partial():
    cfg = AepConfig.from_dict({"run_id": "r1", "model": "m", "boundary": {"max_steps": 10}})
    assert cfg.boundary.max_steps == 10
    assert cfg.boundary.max_cost_usd is None


# ── AepHook ───────────────────────────────────────────────────────────────────

def test_hook_minimal():
    h = AepHook.from_dict({"name": "check-writes", "trigger": "on_tool:write_file"})
    assert h.name == "check-writes"
    assert h.trigger == "on_tool:write_file"
    assert h.timeout_ms == 30000
    assert h.default_verdict == "continue"


def test_hook_full():
    h = AepHook.from_dict({
        "name": "review-turn",
        "trigger": "on_turn_end",
        "timeout_ms": 5000,
        "default_verdict": "stop",
    })
    assert h.timeout_ms == 5000
    assert h.default_verdict == "stop"


def test_hook_round_trip():
    original = {"name": "h1", "trigger": "on_stop", "timeout_ms": 10000, "default_verdict": "inject"}
    h = AepHook.from_dict(original)
    assert h.to_dict() == original


def test_hook_to_dict_always_includes_all_fields():
    h = AepHook(name="h1", trigger="always")
    d = h.to_dict()
    assert "timeout_ms" in d
    assert "default_verdict" in d


def test_hook_missing_name_raises():
    with pytest.raises(ValueError, match="name"):
        AepHook.from_dict({"trigger": "on_stop"})


def test_hook_missing_trigger_raises():
    with pytest.raises(ValueError, match="trigger"):
        AepHook.from_dict({"name": "h1"})


@pytest.mark.parametrize("trigger", [
    "on_start", "on_stop", "on_turn_end", "always",
    "on_tool:bash", "on_tool:write_file", "on_tool:my_custom_tool",
])
def test_hook_trigger_variants(trigger):
    h = AepHook.from_dict({"name": "h", "trigger": trigger})
    assert h.trigger == trigger


@pytest.mark.parametrize("verdict", ["continue", "stop", "inject"])
def test_hook_default_verdict_variants(verdict):
    h = AepHook.from_dict({"name": "h", "trigger": "on_stop", "default_verdict": verdict})
    assert h.default_verdict == verdict


# ── AepConfig ─────────────────────────────────────────────────────────────────

def test_minimal_config():
    cfg = AepConfig.from_dict({"run_id": "r1"})
    assert cfg.run_id == "r1"
    assert cfg.model is None
    assert cfg.prompt is None
    assert cfg.schema_version == "0.2"
    assert cfg.boundary is None
    assert cfg.tags == []
    assert cfg.hooks == []


def test_config_with_model():
    cfg = AepConfig.from_dict({"run_id": "r1", "model": "anthropic/claude-sonnet-4-6"})
    assert cfg.model == "anthropic/claude-sonnet-4-6"


def test_config_without_model_uses_runner_default():
    cfg = AepConfig.from_dict({"run_id": "r1"})
    assert cfg.model is None


def test_prompt_field():
    cfg = AepConfig.from_dict({"run_id": "r1", "prompt": "do it"})
    assert cfg.prompt == "do it"


def test_full_config():
    cfg = AepConfig.from_dict({
        "run_id": "r1", "model": "m",
        "thread_id": "t1", "prompt": "x", "system_prompt": "be helpful",
        "boundary": {"max_cost_usd": 1.5, "max_steps": 30, "max_tokens": 100000},
        "output_schema": {"type": "object"},
        "meta": {"environment": "ci"},
        "tags": ["a"],
    })
    assert cfg.thread_id == "t1"
    assert cfg.meta["environment"] == "ci"
    assert cfg.tags == ["a"]
    assert cfg.boundary is not None
    assert cfg.boundary.max_cost_usd == 1.5
    assert cfg.boundary.max_steps == 30
    assert cfg.boundary.max_tokens == 100000


def test_config_with_single_hook():
    cfg = AepConfig.from_dict({
        "run_id": "r1", "model": "m",
        "hooks": [{"name": "after-write", "trigger": "on_tool:write_file"}],
    })
    assert len(cfg.hooks) == 1
    assert cfg.hooks[0].name == "after-write"
    assert cfg.hooks[0].trigger == "on_tool:write_file"


def test_config_with_multiple_hooks():
    cfg = AepConfig.from_dict({
        "run_id": "r1", "model": "m",
        "hooks": [
            {"name": "h1", "trigger": "on_start"},
            {"name": "h2", "trigger": "on_turn_end", "timeout_ms": 5000},
            {"name": "h3", "trigger": "on_stop", "default_verdict": "stop"},
        ],
    })
    assert len(cfg.hooks) == 3
    assert cfg.hooks[1].timeout_ms == 5000
    assert cfg.hooks[2].default_verdict == "stop"


def test_config_hooks_round_trip():
    d = {
        "run_id": "r1", "model": "m",
        "hooks": [
            {"name": "h1", "trigger": "always", "timeout_ms": 15000, "default_verdict": "continue"},
        ],
    }
    cfg = AepConfig.from_dict(AepConfig.from_dict(d).to_dict())
    assert len(cfg.hooks) == 1
    assert cfg.hooks[0].name == "h1"
    assert cfg.hooks[0].timeout_ms == 15000


def test_config_to_dict_omits_empty_hooks():
    d = AepConfig.from_dict({"run_id": "r1", "model": "m"}).to_dict()
    assert "hooks" not in d


def test_config_to_dict_includes_hooks_when_set():
    cfg = AepConfig.from_dict({
        "run_id": "r1", "model": "m",
        "hooks": [{"name": "h1", "trigger": "on_stop"}],
    })
    d = cfg.to_dict()
    assert "hooks" in d
    assert d["hooks"][0]["name"] == "h1"


def test_missing_run_id_raises():
    with pytest.raises(ValueError, match="run_id"):
        AepConfig.from_dict({"model": "m"})


def test_extra_fields_ignored():
    cfg = AepConfig.from_dict({"run_id": "r1", "model": "m", "future_field": 42})
    assert cfg.run_id == "r1"


def test_round_trip():
    d = {"run_id": "r1", "prompt": "x", "model": "m", "tags": ["t"]}
    cfg = AepConfig.from_dict(AepConfig.from_dict(d).to_dict())
    assert cfg.run_id == "r1"
    assert cfg.prompt == "x"
    assert cfg.tags == ["t"]


def test_to_dict_omits_defaults():
    d = AepConfig.from_dict({"run_id": "r1"}).to_dict()
    assert "model" not in d
    assert "thread_id" not in d
    assert "prompt" not in d
    assert "boundary" not in d
    assert "hooks" not in d


def test_to_dict_includes_model_when_set():
    d = AepConfig.from_dict({"run_id": "r1", "model": "anthropic/claude-sonnet-4-6"}).to_dict()
    assert d["model"] == "anthropic/claude-sonnet-4-6"


def test_to_dict_includes_boundary_when_set():
    d = AepConfig.from_dict({"run_id": "r1", "boundary": {"max_cost_usd": 5.0}}).to_dict()
    assert d["boundary"] == {"max_cost_usd": 5.0}


def test_schema_version_defaults_to_0_2():
    cfg = AepConfig.from_dict({"run_id": "r1", "model": "m"})
    assert cfg.schema_version == "0.2"


def test_schema_version_preserved_when_provided():
    cfg = AepConfig.from_dict({"run_id": "r1", "model": "m", "schema_version": "0.1"})
    assert cfg.schema_version == "0.1"


def test_hook_invalid_in_hook_list_raises():
    with pytest.raises(ValueError):
        AepConfig.from_dict({
            "run_id": "r1", "model": "m",
            "hooks": [{"trigger": "on_stop"}],  # missing name
        })

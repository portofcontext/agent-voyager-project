"""Stateless AVP event emitters.

Each helper accepts a RunState and one SDK message, then emits the
corresponding AVP event(s) via `state.sink`. Nothing is stored here;
all mutable state lives in RunState.

Stage 0: stubs only.
Stage 1: prelude (run_requested, agent_described, agent_started) and
         per-turn (model_turn_started, text_emitted, model_turn_ended,
         agent_stopped) emitters.
Stage 2: tool / subagent emitters.
"""

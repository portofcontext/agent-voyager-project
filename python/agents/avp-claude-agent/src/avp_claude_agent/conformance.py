"""Conformance harness for avp-claude-agent.

Drives `translator.run()` against the real Claude Agent SDK. The
runner is assumed to have:

  - `ANTHROPIC_API_KEY` in env,
  - the `claude` CLI on `PATH`,

i.e. CASDK's normal runtime requirements. There's no scripted SDK
substitute and no fakery — what conformance sees on the wire is what
production sees on the wire.

The per-case workflow is:

  1. Build `Commission`, `AgentDescriptor`, and `ScriptedResolver`
     from the case JSON (the framework's shared parsers).
  2. Run `translator.run()`.
  3. Return the events the translator emitted.

`avp.conformance.sdk_harness` handles case loading, expectation
evaluation, suite iteration, and the CLI.
"""

from __future__ import annotations

from typing import Any

from avp.conformance.harness import SkipCase
from avp.conformance.sdk_harness import (
    build_commission,
    build_descriptor,
    build_resolver,
    make_cli,
    run_case,
    run_suite,
)
from avp_claude_agent.translator import ClaudeAgentTranslator


def _run_one(case: dict[str, Any]) -> list[Any]:
    if case.get("scripted_only"):
        # Cases that need a deterministic model can't be tested against a
        # live LLM (e.g. "force the model to invoke an unknown tool";
        # "trigger stop_reason=refusal on demand"). The AVPAgent
        # reference harness still runs them via `ScriptedModel`.
        raise SkipCase("scripted_only — requires a deterministic-model harness")
    commission = build_commission(case)
    events: list[Any] = []
    translator = ClaudeAgentTranslator(
        commission=commission,
        on_event=events.append,
        resolver=build_resolver(case, commission),
        descriptor=build_descriptor(case),
    )
    translator.run()
    return events


main = make_cli(
    runner=_run_one,
    prog="avp-claude-agent-conformance",
    description="Run v0.1 conformance cases against ClaudeAgentTranslator.",
)


def run_case_for_path(path):
    return run_case(path, _run_one)


def run_suite_for_path(path):
    return run_suite(path, _run_one)


__all__ = ["main", "run_case_for_path", "run_suite_for_path"]

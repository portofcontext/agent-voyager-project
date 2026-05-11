"""Example 11 — drop-in instrumentation for an existing OpenAI Agents SDK run.

Companion to example 10 (which drives the full translator end-to-end via
its `.run()`). Example 11 shows the lighter-touch shape: you already have
working `agents.Runner` code; you just want AVP events on the wire.

The change to add AVP: wrap the call in `with AVPTracer(...)` and use
`traced_openai_runner()` (no args) instead of `Runner.run_sync(...)`. The
factory pulls Commission from the active tracer; the SDK's `RunHooks`
emit AVP events as turns and tools fire.

Run:
  OPENAI_API_KEY=... python examples/11_openai_agents_traced_client.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import UTC, datetime

from avp_openai_agent import traced_openai_runner

from avp import AVPTracer, Commission, print_event


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("error: set OPENAI_API_KEY before running this example", file=sys.stderr)
        return 2
    if importlib.util.find_spec("agents") is None:
        print(
            "error: install openai-agents (pip install openai-agents)",
            file=sys.stderr,
        )
        return 2

    from openai.types.shared.reasoning import Reasoning

    from agents import Agent, ModelSettings  # type: ignore[import-not-found]

    commission = Commission(
        schema_version="0.1",
        run_id=f"traced-openai-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
        model="gpt-5-nano",
        prompt=(
            "Greet the user with the single word 'hello', then add one "
            "short sentence about what observability means in agent runs. "
            "End with DONE."
        ),
    )

    # Compare to a plain Runner.run_sync flow:
    #
    #     agent = Agent(name="x", instructions="...", model="gpt-5-nano")
    #     result = Runner.run_sync(agent, prompt)
    #
    # Two changes:
    #   - wrap with `AVPTracer(commission, on_event=...)` (sets active tracer)
    #   - `traced_openai_runner()` replaces direct `Runner.run_sync`;
    #     Commission flows from the active tracer.
    # `reasoning.summary="auto"` asks OpenAI to return the model's
    # reasoning summary alongside the answer. Without it, GPT-5 still
    # reasons server-side and you still pay reasoning tokens, but the
    # API returns an empty summary — so AVP emits reasoning_emitted
    # with `avp.reasoning.redacted=true` (honest, but not very useful
    # for an audit demo). Set `concise` or `detailed` to control
    # verbosity; reasoning summaries cost a small number of extra
    # output tokens.
    agent = Agent(
        name="avp-traced-agent",
        instructions="",
        model="gpt-5-nano",
        model_settings=ModelSettings(reasoning=Reasoning(summary="auto")),
    )

    with AVPTracer(commission, on_event=print_event), traced_openai_runner() as t:
        result = t.run_sync(agent, commission.prompt)

    print(f"\nfinal output: {result.final_output!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

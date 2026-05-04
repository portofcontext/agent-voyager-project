"""Driver-pattern AEP runner — minimal template.

Use this as the starting shape when you OWN the agent loop and call an LLM
SDK each turn. The reference implementation against the Anthropic SDK lives at
python/runners/aep-anthropic/. This template is provider-agnostic.

You implement ONE thing: ModelDriver.step(history) -> ModelResponse. The
AEPRunner does the rest — lifecycle events, boundary enforcement, verifier
scheduling, RPC tool routing, NDJSON emission.

To run:
    pip install -e python/aep
    python examples/driver-runner-template.py
"""

from __future__ import annotations

from typing import Any

from aep import Config
from aep.runner import AEPRunner
from aep.runner.drivers import ModelDriver, ModelResponse, ScriptedToolCall
from aep.runner.mock import ScriptedSupervisor, ScriptedTools

# ── Implement a ModelDriver against your LLM ────────────────────────────────


class MyModelDriver(ModelDriver):
    """Replace this with calls to your real LLM SDK.

    Per AEP §10.4: tokens_input MUST include cache-read tokens (they ARE
    input tokens; cache changes billing, not work). cost_usd is the BILLABLE
    cost after cache discounts.
    """

    def __init__(self, model: str = "your-model-id") -> None:
        self.model = model
        self._turn = 0

    def step(self, history: list[dict[str, Any]]) -> ModelResponse:
        self._turn += 1
        # ── Your LLM call goes here ─────────────────────────────────────────
        # response = your_sdk.complete(model=self.model, messages=history, tools=...)
        # text = response.content_text
        # tool_calls = [
        #     ScriptedToolCall(call_id=t.id, tool=t.name, input=t.arguments)
        #     for t in response.tool_calls
        # ]
        # ────────────────────────────────────────────────────────────────────
        # Below is a deterministic stub so the template runs without an SDK.
        text = f"stubbed turn {self._turn}"
        tool_calls: list[ScriptedToolCall] = []
        converged = self._turn >= 1

        return ModelResponse(
            tokens_input=120,  # MUST include cache reads, per §10.4
            tokens_output=40,
            cost_usd=0.0006,  # billable cost (post-cache-discount)
            duration_ms=800,
            text=text,
            tool_calls=tool_calls,
            tokens_cache_read=None,  # set when your SDK reports it
            tokens_cache_write=None,
            converged=converged,
        )


# ── Wire up + run ────────────────────────────────────────────────────────────


def main() -> None:
    config = Config(
        schema_version="0.1",
        run_id="demo-driver-runner",
        model="your-model-id",
        prompt="Refactor the auth module.",
        # Environment primitives — supervisor declares; agent enforces.
        boundary={"max_cost_usd": 0.50, "max_steps": 10},
        verifiers=[
            {
                "name": "tests-pass",
                "trigger": "after_each_turn",
                "source": {"shell": "true"},  # replace with `cargo test` etc.
                "on_failure": "halt",
            },
        ],
    )

    runner = AEPRunner(
        config=config,
        model=MyModelDriver(model="your-model-id"),
        tools=ScriptedTools(),  # plug in a real ToolDriver if needed
        supervisor=ScriptedSupervisor(
            []
        ),  # plug in a real SupervisorDriver if RPC tools/observations
    )

    stop = runner.run()
    print(
        f"\nrun ended: reason={stop.reason!r}, "
        f"turns={stop.state.total_turns}, "
        f"cost=${stop.state.total_cost_usd:.6f}"
    )
    print(f"trajectory length: {len(runner.trajectory)} events")


if __name__ == "__main__":
    main()

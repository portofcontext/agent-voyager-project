# avp-anthropic — AVP v0.1 agent for the Anthropic Messages API

This package wraps the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) so it speaks AVP v0.1.

**Pattern: driver.** This agent owns the agent loop. The reference `AVPAgent` (from the [`avp`](../../avp/) package) drives the loop and calls `AnthropicModelDriver.step()` once per turn. The driver translates AVP history ↔ Anthropic messages, calls `client.messages.create(...)`, and translates the response ↔ AVP `ModelResponse`. The agent does the rest (events, MCP/tool dispatch, subagent lifecycle).

## Install

This package is part of the AVP uv workspace; bootstrap from the repo root:

```bash
uv sync
export ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)"   # or set the env var directly
```

Once published, the standalone install will be `pip install avp-anthropic`. Until
then, work from a checkout of the workspace.

## Quick start (programmatic)

```python
from avp import Commission
from avp.agent import AVPAgent
from avp.agent.mock import ScriptedTools, ScriptedSupervisor   # or your own drivers
from avp_anthropic import AnthropicModelDriver

config = Commission(
    schema_version="0.1",
    run_id="my-run",
    model="claude-sonnet-4-6",
    prompt="Refactor the auth module.",
)

agent = AVPAgent(
    config=config,
    model=AnthropicModelDriver(),
    tools=ScriptedTools(),                    # or your real ToolDriver
    supervisor=ScriptedSupervisor([]),         # or your real SupervisorDriver
)
stop_event = agent.run()
print(f"stopped: {stop_event.reason}")
```

## CLI (stdio)

```bash
echo '<config json>' | avp-anthropic   # runs and emits NDJSON events on stdout
```

This is what your Rust DDD supervisor pipes against:

```
your-supervisor ──stdin (Commission + SupervisorMessages)──▶ avp-anthropic
                ◀──stdout (NDJSON Event trajectory)─── avp-anthropic
```

## What this agent translates

| Anthropic API | AVP v0.1 |
|---|---|
| `client.messages.create(...)` per turn | `model_turn_started` / `model_turn_ended` |
| `response.usage.input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | `model_turn_ended.tokens_input` (cache-read INCLUDED), `tokens_output`, `tokens_cache_read`, `tokens_cache_write` |
| Cost (model × tokens via local pricing table) | `model_turn_ended.cost_usd` |
| `content` blocks of type `tool_use` | `tool_invoked` events (one per block) |
| `content` blocks of type `text` | `text_emitted` |
| `stop_reason == "end_turn"` (no tool calls) | terminal turn → `agent_stopped reason="converged"` |
| `stop_reason == "tool_use"` | continue, agent dispatches tools |

Tools declared on `Commission.tools` (supervisor-executed) become Anthropic `tools` parameter on each call. Tools the agent registers locally (via `ToolDriver.is_local`) also go into the same `tools` parameter; the agent dispatches the call to the local driver and returns the result via a follow-up `tool_result` content block.

## Pricing table

Hardcoded per-model rates (`USD per 1M tokens`) for the latest Claude family:

| Model | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| `claude-opus-4-7` | $15.00 | $75.00 | $1.50 | $18.75 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | $0.30 | $3.75 |
| `claude-haiku-4-5-20251001` | $1.00 | $5.00 | $0.10 | $1.25 |

Unknown models fall back to `0.0` and emit a warning. Override via `AnthropicModelDriver(prices={...})`.

## Tests

Run from the repo root (where `uv sync` was bootstrapped). Both forms work — pick whichever reads cleaner:

```bash
# Driver-translation + CLI smoke + multi-turn tests (mock Anthropic client, free)
uv run pytest python/agents/avp-anthropic -m "not real_llm"

# Real-LLM smoke tests (hit the live API)
ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)" \
  uv run pytest python/agents/avp-anthropic -m real_llm
```

The mock-client tests assert wire-format correctness — what AVP events the driver emits given specific Anthropic responses. The real-LLM smoke tests assert end-to-end integration against actual Claude responses, including cost/token accounting and cache-token math (per SPEC.md §10.4). They use `claude-haiku-4-5-20251001` (cheapest current model).

The conformance suite at [`conformance/v0.1/`](../../../conformance/v0.1/) tests AVP wire-level behavior using the [`avp` package's reference agent](../../avp/), not this one — passing it does not automatically certify `avp-anthropic`.

# aep-anthropic — AEP v0.1 runner for the Anthropic Messages API

This package wraps the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) so it speaks AEP v0.1.

**Pattern: driver.** This runner owns the agent loop. The reference `AEPRunner` (from the [`aep`](../../aep/) package) drives the loop and calls `AnthropicModelDriver.step()` once per turn. The driver translates AEP history ↔ Anthropic messages, calls `client.messages.create(...)`, and translates the response ↔ AEP `ModelResponse`. The runner does the rest (events, supervisor-tools via RPC, verifiers, boundary).

## Install

```bash
pip install aep-anthropic
export ANTHROPIC_API_KEY=...
```

## Quick start (programmatic)

```python
from aep import Config
from aep.runner import AEPRunner
from aep.runner.mock import ScriptedTools, ScriptedSupervisor   # or your own drivers
from aep_anthropic import AnthropicModelDriver

config = Config(
    schema_version="0.1",
    run_id="my-run",
    model="claude-sonnet-4-6",
    prompt="Refactor the auth module.",
    boundary={"max_cost_usd": 2.0, "max_steps": 30},
)

runner = AEPRunner(
    config=config,
    model=AnthropicModelDriver(),
    tools=ScriptedTools(),                    # or your real ToolDriver
    supervisor=ScriptedSupervisor([]),         # or your real SupervisorDriver
)
stop_event = runner.run()
print(f"stopped: {stop_event.reason}")
```

## CLI (stdio)

```bash
echo '<config json>' | aep-anthropic   # runs and emits NDJSON events on stdout
```

This is what your Rust DDD supervisor pipes against:

```
your-supervisor ──stdin (Config + SupervisorMessages)──▶ aep-anthropic
                ◀──stdout (NDJSON Event trajectory)─── aep-anthropic
```

## What this runner translates

| Anthropic API | AEP v0.1 |
|---|---|
| `client.messages.create(...)` per turn | `model_turn_started` / `model_turn_ended` |
| `response.usage.input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | `model_turn_ended.tokens_input` (cache-read INCLUDED), `tokens_output`, `tokens_cache_read`, `tokens_cache_write` |
| Cost (model × tokens via local pricing table) | `model_turn_ended.cost_usd` |
| `content` blocks of type `tool_use` | `tool_invoked` events (one per block) |
| `content` blocks of type `text` | `text_emitted` |
| `stop_reason == "end_turn"` (no tool calls) | terminal turn → `agent_stopped reason="converged"` |
| `stop_reason == "tool_use"` | continue, runner dispatches tools |

Tools declared on `Config.tools` (supervisor-executed) become Anthropic `tools` parameter on each call. Tools the runner registers locally (via `ToolDriver.is_local`) also go into the same `tools` parameter; the runner dispatches the call to the local driver and returns the result via a follow-up `tool_result` content block.

## Pricing table

Hardcoded per-model rates (`USD per 1M tokens`) for the latest Claude family:

| Model | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| `claude-opus-4-7` | $15.00 | $75.00 | $1.50 | $18.75 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | $0.30 | $3.75 |
| `claude-haiku-4-5-20251001` | $1.00 | $5.00 | $0.10 | $1.25 |

Unknown models fall back to `0.0` and emit a warning. Override via `AnthropicModelDriver(prices={...})`.

## Tests

```bash
# Driver-translation tests (mock Anthropic client, free)
pytest -m "not real_llm"

# Real-LLM smoke tests (hit the live API, cost ~$0.001 per run)
ANTHROPIC_API_KEY=sk-... pytest -m real_llm
```

The mock-client tests assert wire-format correctness — what AEP events the driver emits given specific Anthropic responses. The real-LLM smoke tests assert end-to-end integration against actual Claude responses, including cost/token accounting, boundary enforcement, and cache-token math (per SPEC.md §10.4). They use `claude-haiku-4-5-20251001` (cheapest current model) and tight boundaries.

The conformance suite at [`conformance/v0.1/`](../../../conformance/v0.1/) tests AEP wire-level behavior using the [`aep` package's reference runner](../../aep/), not this one — passing it does not automatically certify `aep-anthropic`.

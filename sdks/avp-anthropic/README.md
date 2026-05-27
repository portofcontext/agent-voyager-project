# avp-anthropic: AVP v0.1 SDK adapter for the Anthropic Messages API

This package is the thin AVP adapter for the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python). The Anthropic Messages API is a raw HTTP client: no agent loop, no built-in tools. This package matches that. It ships a per-turn translator (`AnthropicModelDriver`), a drop-in traced client (`AnthropicTracedClient` / `wrap_anthropic`), the `ModelResponse` to wire converters (`model_response_to_content` / `model_response_usage`), Commission-to-API translators, and a `build_descriptor` helper. It does NOT ship an agent loop, a CLI, or built-in tools. Agents wrap it.

For a worked example of an agent built on this adapter, see [`_anthropic_reference_agent.py`](../../supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py). It defines a local `ShellTools` (bash / read_file / write_file) and inlines its own loop over `AnthropicModelDriver`, emitting events to a sink. Example 01 spawns it as a subprocess.

## Install

This package is part of the AVP uv workspace, rooted at the repo root. Bootstrap from there:

```bash
make sync
export ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)"   # or set the env var directly
```

Once published, the standalone install will be `pip install avp-anthropic`. Until then, work from a checkout of the workspace.

## Two ways to use it

### 1. As a per-turn translator inside your own loop

Use this when you're building a new agent. `AnthropicModelDriver.step(history)` translates one turn between AVP history and the Anthropic Messages API and returns a `ModelResponse`; your loop owns the rest (emit the events, dispatch tools, accumulate history, decide when to stop). The wire-types binding ships no agent base class, so the loop is yours to inline.

```python
from avp_anthropic import (
    AnthropicModelDriver,
    model_response_to_content,
    model_response_usage,
)

driver = AnthropicModelDriver(model="claude-sonnet-4-6", tools_param=[...])

# Per turn, inside your loop:
mr = driver.step(history)                 # one Anthropic turn -> ModelResponse
content = model_response_to_content(mr)    # -> assistant_message.avp.content blocks
usage = model_response_usage(mr)           # -> assistant_message.avp.usage
# emit assistant_message(content, usage, cost_usd=mr.cost_usd), then dispatch
# mr.tool_calls, append their results to history, and repeat until mr.converged.
```

The reference agent's `run_agent` in [`_anthropic_reference_agent.py`](../../supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py) is the worked-out version of this loop, including the prelude, tool dispatch, and stop handling.

### 2. As a drop-in tracer over an existing Anthropic SDK loop

Use this when you have an existing Anthropic SDK loop you don't want to restructure. Wrap your client with `AnthropicTracedClient` (or `wrap_anthropic` at module load), give it a Commission and an `on_event` sink, and the loop emits AVP events.

```python
import anthropic
from avp import Commission
from avp_anthropic import AnthropicTracedClient, print_event

commission = Commission(schema_version="0.1", run_id="traced-run", model="claude-sonnet-4-6")
with AnthropicTracedClient(anthropic.Anthropic(), commission=commission, on_event=print_event) as client:
    resp = client.messages.create(model=commission.model, max_tokens=300, messages=[...])
    # `client.tool(...)` / `client.subagent(...)` record tool + subagent spans.
    client.converged()
```

See `examples/06_anthropic_traced_client.py` for an end-to-end run.

## What the SDK adapter translates

| Anthropic API | AVP v0.1 |
|---|---|
| `client.messages.create(...)` per turn | one `assistant_message` event |
| `response.usage.{input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}` | `assistant_message.avp.usage` (cache-read AND cache-write INCLUDED in `input_tokens`: the SDK reports `input_tokens` as fresh-only, so cached and newly-cached tokens are added back) |
| Cost (model x tokens via the local pricing table) | `assistant_message.avp.cost_usd` (+ `avp.cost.source`) |
| `content` blocks of type `text` | a `TextBlock` in `assistant_message.avp.content` |
| `content` blocks of type `tool_use` | a `ToolUseBlock` in `avp.content`; the loop dispatches it and emits `tool_invoked` / `tool_returned` |
| `stop_reason == "end_turn"` (no tool calls) | terminal turn, `agent_stopped reason="converged"` |
| `stop_reason == "tool_use"` | continue; the loop dispatches tools |

The driver also parses extended-thinking blocks (a `ThinkingBlock` in `avp.content`), refusal-flavored stop reasons (a `RefusalBlock` plus `agent_stopped reason="refused"`), MCP `mcp_tool_use` / `mcp_tool_result` blocks, and hosted server-side tool blocks (`web_search`, `code_execution`, `bash_code_execution`), which surface as `ServerToolUseBlock` / `ServerToolResultBlock` in `avp.content`.

## SDK options pass-through

`AnthropicModelDriver` accepts two escape-hatch dicts for SDK-specific concerns AVP intentionally doesn't put on the wire (per [`avp/core/spec/v0.1/README.md`](../../avp/core/spec/v0.1/README.md) deployment scope):

```python
driver = AnthropicModelDriver(
    model="claude-sonnet-4-6",
    extra_client_kwargs={
        # Merged into anthropic.Anthropic(...) at lazy client construction.
        # Client-level concerns: timeout, retries, base URL, custom HTTP
        # headers. Ignored if you pass `client=` directly.
        "timeout": 60.0,
        "max_retries": 3,
    },
    extra_kwargs={
        # Merged into each messages.create(...) call. Per-request knobs.
        "temperature": 0.0,
        "top_p": 0.95,
    },
)
```

This is the analog of `avp-claude-agent-sdk`'s deployment-layer config that doesn't translate to a wire-format concept (same purpose, different SDK surface). AVP wire-shape fields the driver populates per turn (`model`, `max_tokens`, `messages` and `system` from AVP history, `tools` from `tools_param` plus any subagents resolved via `set_resolved_assets`, `mcp_servers` from resolver-returned HTTP MCP material) take precedence: `extra_kwargs` cannot override them, since doing so would let a supervisor silently desync the trajectory from what the model actually saw.

## Pricing table

Per-model rates come from the bundled `avp` price table (shared with `avp-claude-agent-sdk`), keyed `<provider>/<model>` and synced from models.dev. A bare Anthropic model is resolved with `provider="anthropic"`. Unknown models fall back to `0.0` with a warning and `avp.cost.source = "unknown"`. Override via `AnthropicModelDriver(prices={...})`.

## Tests

Run from the repo root (where `make sync` was bootstrapped):

```bash
# Driver-translation + traced-client + history-render tests (mock Anthropic client, free)
(cd sdks/avp-anthropic && uv run pytest -m "not real_llm")

# Real-LLM smoke tests (hit the live API)
ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)" \
  sh -c 'cd sdks/avp-anthropic && uv run pytest -m real_llm'
```

The mock-client tests assert wire-format correctness: what AVP events the driver and traced client emit given specific Anthropic responses (including the token/cost parity between the two). The real-LLM smoke tests assert end-to-end integration against actual Claude responses, including cost/token accounting and cache-token math (per [`avp/core/spec/v0.1/trajectory.md`](../../avp/core/spec/v0.1/trajectory.md)). They use `claude-haiku-4-5-20251001` (cheapest current model).

CLI-level smoke tests for the reference agent live in [`test_reference_agent.py`](../../supervisors/simple-supervisor-example/tests/test_reference_agent.py): describe, invalid-Commission handling, tool round-trips, NDJSON envelope shape.

The cross-agent conformance suite at [`avp/core/conformance/`](../../avp/core/conformance/) certifies AVP wire-level behavior by driving a conforming agent (e.g. `avp-claude-agent-sdk` or `avp-goose`) against a real model. It certifies the agent, not this adapter directly; an agent built on `avp-anthropic` is certified by running the suite against that agent.
```

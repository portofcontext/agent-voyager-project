# avp-anthropic: AVP v0.1 SDK adapter for the Anthropic Messages API

This package is the thin AVP adapter for the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python). The Anthropic Messages API is a raw HTTP client: no agent loop, no built-in tools. This package matches that: it ships a `ModelDriver`, a `TracedClient`, Commission-to-API translators, and a `build_descriptor` helper. It does NOT ship an agent loop, a CLI, or built-in tools. Agents wrap it.

For a worked example of an agent built on this adapter, see [`python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py`](../../supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py). It defines a local `ShellTools` (bash / read_file / write_file), constructs an `AVPAgent` with `AnthropicModelDriver`, and runs the loop. Examples 01 and 05 spawn it.

## Install

This package is part of the AVP uv workspace (rooted at [`python/`](../../) so the repo root stays language-agnostic). Bootstrap from the repo root:

```bash
make sync            # uv --directory python sync
export ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)"   # or set the env var directly
```

Once published, the standalone install will be `pip install avp-anthropic`. Until then, work from a checkout of the workspace.

## Two ways to use it

### 1. As a `ModelDriver` plugged into `AVPAgent`

Use this when you're building a new agent and want AVPAgent's loop. The driver translates one turn between AVP history and the Anthropic Messages API; the loop, the tool dispatch, and the event emission all live in AVPAgent.

```python
from avp import Commission
from avp.agent import AVPAgent
from avp.agent.mock import ScriptedTools, ScriptedSupervisor
from avp_anthropic import AnthropicModelDriver, build_descriptor

commission = Commission(
    schema_version="0.1",
    run_id="my-run",
    model="claude-sonnet-4-6",
    prompt="Refactor the auth module.",
)

agent = AVPAgent(
    commission=commission,
    model=AnthropicModelDriver(),
    tools=ScriptedTools(),                 # or your real ToolDriver
    supervisor=ScriptedSupervisor(),       # or your real SupervisorDriver
    descriptor=build_descriptor(
        agent_name="my-agent",
        agent_version="0.1.0",
        built_in_tools=[...],              # MCP-shaped entries; the helper layers in
                                           # hosted-tool kinds + thinking capability
    ),
)
agent.run()
```

The reference agent in `examples/_anthropic_reference_agent.py` is the worked-out version of this pattern.

### 2. As a drop-in tracer over an existing Anthropic SDK loop

Use this when you have an existing Anthropic SDK loop you can't restructure around AVPAgent. Wrap your client with `AnthropicTracedClient` (or `wrap_anthropic` at module load), give it a Commission and an `on_event` sink, and the loop emits AVP events.

```python
import anthropic
from avp import Commission, print_event
from avp_anthropic import AnthropicTracedClient

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
| `client.messages.create(...)` per turn | `model_turn_started` / `model_turn_ended` |
| `response.usage.input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | `model_turn_ended.tokens_input` (cache-read AND cache-write INCLUDED — the SDK reports `input_tokens` as fresh-only, so cached and newly-cached tokens are added back), `tokens_output`, `tokens_cache_read`, `tokens_cache_write` |
| Cost (model x tokens via local pricing table) | `model_turn_ended.cost_usd` |
| `content` blocks of type `tool_use` | `tool_invoked` events (one per block) |
| `content` blocks of type `text` | `text_emitted` |
| `stop_reason == "end_turn"` (no tool calls) | terminal turn, `agent_stopped reason="converged"` |
| `stop_reason == "tool_use"` | continue, agent dispatches tools |

The driver also parses extended-thinking blocks (`reasoning_emitted`), refusal-flavored stop reasons (`refusal_recorded`), MCP `mcp_tool_use` / `mcp_tool_result` blocks, and hosted server-side tool blocks (`web_search`, `code_execution`, `bash_code_execution`).

## SDK options pass-through

`AnthropicModelDriver` accepts two escape-hatch dicts for SDK-specific concerns AVP intentionally doesn't put on the wire (per [`spec/README.md` §6](../../../spec/README.md) deployment scope):

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

This is the analog of `avp-claude-agent`'s `extra_sdk_options` (same purpose, deployment-layer config that doesn't translate to a wire-format concept; different SDK surface). AVP wire-shape fields the driver populates per turn (`model`, `max_tokens`, `messages` and `system` from AVP history, `tools` from `tools_param` plus any subagents resolved via `set_resolved_assets`, `mcp_servers` from resolver-returned HTTP MCP material) take precedence — `extra_kwargs` cannot override them, since doing so would let a supervisor silently desync the trajectory from what the model actually saw.

## Pricing table

Hardcoded per-model rates (`USD per 1M tokens`) for the latest Claude family, shared with `avp-claude-agent` via the `avp` package:

| Model | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| `claude-opus-4-7` | $15.00 | $75.00 | $1.50 | $18.75 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | $0.30 | $3.75 |
| `claude-haiku-4-5-20251001` | $1.00 | $5.00 | $0.10 | $1.25 |

Unknown models fall back to `0.0` and emit a warning. Override via `AnthropicModelDriver(prices={...})`.

## Tests

Run from the repo root (where `make sync` was bootstrapped):

```bash
# Driver-translation + traced-client + multi-turn tests (mock Anthropic client, free)
(cd python/sdks/avp-anthropic && uv run pytest -m "not real_llm")

# Real-LLM smoke tests (hit the live API)
ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)" \
  (cd python/sdks/avp-anthropic && uv run pytest -m real_llm)
```

The mock-client tests assert wire-format correctness: what AVP events the driver emits given specific Anthropic responses. The real-LLM smoke tests assert end-to-end integration against actual Claude responses, including cost/token accounting and cache-token math (per [`spec/trajectory/v0.1/trajectory.md` §3.3](../../../spec/trajectory/v0.1/trajectory.md#33-cost--token-accounting-rules-normative)). They use `claude-haiku-4-5-20251001` (cheapest current model).

CLI-level smoke tests for the reference agent live in [`python/supervisors/simple-supervisor-example/tests/test_reference_agent.py`](../../supervisors/simple-supervisor-example/tests/test_reference_agent.py): describe, invalid-Commission handling, tool round-trips, NDJSON envelope shape.

The conformance suite at [`conformance/`](../../../conformance/) tests AVP wire-level behavior using the [`avp` package's reference agent](../../avp/), not this adapter; passing it does not automatically certify an agent built on `avp-anthropic`.

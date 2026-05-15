# avp-openai-agent

AVP v0.1 agent for the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
(PyPI: `openai-agents`, import: `agents`).

## Why this exists

The OpenAI Agents SDK owns its own agent loop, tool dispatch, and handoff
orchestration, just like the Claude Agent SDK. The right shape for an AVP
package on top of it is the **observer pattern**: subclass `RunHooks`,
intercept the SDK's lifecycle callbacks, and translate them into AVP v0.1
events. This package does not own the loop.

This mirrors [`avp-claude-agent`](../avp-claude-agent/) for the Anthropic
side. For the raw OpenAI Responses API (no agent loop), see
[`avp-openai`](../../sdks/avp-openai/) — an SDK adapter that ships a
`ModelDriver` and `TracedClient` instead of a full agent.

## Usage

```python
from agents import Agent, Runner
from avp import Commission, print_event
from avp_openai_agent import OpenAIAgentTranslator

commission = Commission(
    schema_version="0.1",
    run_id="demo",
    model="gpt-5-nano",
    prompt="Say 'pong' and nothing else.",
)

translator = OpenAIAgentTranslator(commission, on_event=print_event)
translator.run()
```

The translator builds an `agents.Agent`, runs it via `Runner.run_sync(...)`
with itself registered as `RunHooks`, and emits AVP events as the SDK
progresses.

### Drop-in observability over an existing run

```python
from agents import Agent, Runner
from avp import AVPTracer
from avp_openai_agent import TracedOpenAIRunner

with TracedOpenAIRunner(commission=commission, on_event=publish) as runner:
    result = runner.run_sync(agent, "say hi")
```

### CLI

```
avp-openai-agent describe              # print AgentDescriptor JSON
echo '{...commission...}' | avp-openai-agent   # run, stream NDJSON
```

## Spec mapping

| OpenAI Agents SDK | AVP event |
|---|---|
| `RunHooks.on_agent_start` | `agent_started` |
| `RunHooks.on_agent_end` | `agent_stopped` |
| `RunHooks.on_llm_start` | `model_turn_started` |
| `RunHooks.on_llm_end` | `model_turn_ended` + `cost_recorded` + `text_emitted` + `reasoning_emitted` |
| `RunHooks.on_tool_start` | `tool_invoked` |
| `RunHooks.on_tool_end` | `tool_returned` |
| `RunHooks.on_handoff` | `subagent_invoked` (next `on_agent_end` of that target → `subagent_returned`) |

Handoffs map to AVP subagent semantics so the wire stays frozen at v0.1.

# agent-execution-protocol (Python)

Python SDK for the Agent Execution Protocol. Provides typed config and event
dataclasses, NDJSON emit helpers, a stream reader, and a compliance validator.

## Install

```bash
uv pip install agent-execution-protocol
```

## Usage

### Emit events from a runner

```python
from agent_execution_protocol import (
    emit_agent_start,
    emit_tool_call,
    emit_tool_result,
    emit_cost_update,
    emit_agent_stop,
)

emit_agent_start(run_id="r1", model="anthropic/claude-sonnet-4-6", prompt="Fix the bug")

emit_tool_call(run_id="r1", step=1, call_id="c1", tool="bash", input={"command": "pytest"})
emit_tool_result(run_id="r1", step=1, call_id="c1", tool="bash", output="5 passed", duration_ms=420)

emit_cost_update(run_id="r1", total_cost_usd=0.012, total_tokens=4200)
emit_agent_stop(run_id="r1", reason="converged", total_tokens=4200,
                total_cost_usd=0.012, total_turns=3, duration_ms=8100)
```

### Read a config from stdin

```python
from agent_execution_protocol import AepConfig, read_config

raw = read_config()           # reads one JSON line from stdin
config = AepConfig.from_dict(raw)
print(config.model, config.prompt)
```

### Parse and validate a trajectory

```python
from agent_execution_protocol import parse_stream, validate

with open("trajectory.jsonl") as f:
    events, errors = parse_stream(f.read())

violations = validate(events)
for v in violations:
    print(v)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

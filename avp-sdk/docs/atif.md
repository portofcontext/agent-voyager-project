# Native ATIF trajectories

AVP produces [ATIF-v1.8](../../spec/v0.1/trajectory.md) directly. Both SDKs,
all built-in adapters, and the supervisor CLI use the same document. There is
no export step or separate event format.

```sh
avp-pydantic-ai-cli run --commission commission.json --out trajectory.json
```

The agent writes one ATIF document when the run ends. Tool calls are in a
model-response step's `tool_calls`; their results are attached to that step's
`observation`. The Commission and the Descriptor are in `extra.avp`. Images
and skill directories are files beside the document; keep them together when
moving a run.

## Read a trajectory

```python
from pathlib import Path
from avp.trajectory import final_output, parse_trajectory

trajectory = parse_trajectory(Path("trajectory.json").read_text())
for step in trajectory.steps:
    if step.source == "agent":
        print(step.message, step.metrics)
print(final_output(trajectory))
```

Python includes a copy of Harbor's Pydantic models, with each `extra` typed by
AVP's models, so `step.extra.avp.error_code` is checked when read. TypeScript
exports the same data types, `parseTrajectory`, and `finalOutput` from
`@agent-voyager-project/sdk/trajectory`.

## Use existing ATIF tools

Install Harbor in a separate environment and validate the ordinary run file:

```sh
uv tool install 'harbor @ git+https://github.com/harbor-framework/harbor.git@9c7a39b991d7e2205019f6be0598cbd22d84bfc3'
uv run --with harbor python -m harbor.utils.trajectory_validator trajectory.json
```

Harbor's `extract_conversations_from_trajectory` reads this file directly for
training-data extraction. Harbor's viewer expects a job/trial directory with
`agent/trajectory.json` and job metadata; that directory layout is separate
from ATIF. See the [ecosystem example](../../examples/atif/README.md) for viewing
and extracting conversations without changing the trajectory document.

ATIF tools can read the data a runtime reports. This doesn't mean one runtime
can resume another runtime's session. Harbor's text
trace exporter rejects images; use a multimodal consumer for those runs.

## Information retained

Standard ATIF fields hold messages, reasoning, tool calls, results, subagent
trajectories, the model, tool definitions, usage, and cost. `extra.avp` holds
what ATIF has no field for, as the [trajectory spec](../../spec/v0.1/trajectory.md#3-reference)
defines: the Commission and Descriptor, the run's MCP servers, skills, and
subagents, tool fields the OpenAI function shape lacks, stop reason, output
with its JSON type, error codes, timing, cache-write and reasoning tokens,
citations, and reasoning signatures.

Unknown usage is left out, not zero. A subagent's reported totals are used only
when its responses are hidden. Each skill's `source` points to its copied
directory beside the document:

```python
for skill in trajectory.agent.extra.avp.skills or []:
    print(skill.name, skill.source)
```

## Tests and Harbor updates

`make check` runs shared Recorder cases, Python and TypeScript validation tests,
and all eight adapter suites. It also checks that external Harbor
trajectories load without AVP extensions. Native CLI integration jobs and live
provider checks exercise runtime-specific behavior.

The copied Harbor models and their license are in `avp/_vendor/atif`. Run
`scripts/vendor-atif.py` with the pinned Harbor checkout, which also types each
`extra`, then `make schemas bindings` when updating them. The Harbor example trajectory and schema source
are documented in [`testdata/atif`](../testdata/atif/README.md).

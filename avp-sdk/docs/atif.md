# Native ATIF trajectories

AVP produces [ATIF-v1.8](../../spec/v0.1/trajectory.md) directly. Both SDKs,
all built-in adapters, and the supervisor CLI use the same document. There is
no export step, old AVP event envelope, or source-event archive.

```sh
avp-pydantic-ai-cli run --commission commission.json --out trajectory.json
```

File output is an atomically replaced JSON snapshot. Tools first appear in a
model-response step's `tool_calls`; their results are attached to that step's
`observation`. The CLI follows these updates without replaying previous output.
Stdout output is one completed document. Images are deduplicated files beside
the document, so move the referenced assets with it.

## Read a trajectory

```python
from pathlib import Path
from avp.trajectory import parse_trajectory

trajectory = parse_trajectory(Path("trajectory.json").read_text())
for step in trajectory.steps:
    if step.source == "agent":
        print(step.message, step.metrics)
```

Python uses Harbor's vendored upstream Pydantic models. TypeScript exports the
same wire shape and `parseTrajectory` from `@agent-voyager-project/sdk/trajectory`.
`avp.reports` and `@agent-voyager-project/sdk/reports` define Recorder method inputs
for adapter authors; these inputs are not another persisted wire format.

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

ATIF interoperability covers data the runtime actually exposes. It does not
make every runtime support resuming another runtime's session. Harbor's text
trace exporter rejects images; use a multimodal consumer for those runs.

## Information retained

Standard ATIF fields carry messages, public reasoning, tool calls, observations,
child trajectories, model identity, tool schemas, usage, and cost. `extra.avp`
retains typed final output, terminal reason, errors, timing, effective settings,
MCP ownership, cache-write/reasoning-token distinctions, and provider annotations.
Unknown usage is omitted. Opaque child usage is counted only when individual
child responses are unavailable.

The original Commission and full Descriptor are not duplicated. The CLI stores
the Commission separately. No copy of native runtime events is required.

## Verification and upstream updates

`make check` exercises shared Recorder fixtures, Python and TypeScript semantic
validation, and all eight adapter suites. It also checks that external Harbor
trajectories load without AVP extensions. Native CLI integration jobs and live
provider checks exercise runtime-specific behavior.

Upstream models and licenses live in `avp/_vendor/atif`. Run
`scripts/vendor-atif.py` with the pinned Harbor checkout, then `make schemas
bindings` when updating them. The upstream golden fixture and schema provenance
are documented in [`testdata/atif`](../testdata/atif/README.md).

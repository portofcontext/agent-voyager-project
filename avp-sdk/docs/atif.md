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
Stdout output is one completed document. File output also writes `artifacts.json`
and captured files beside the trace. Move the manifest and all listed files
with the trajectory to preserve the complete run.

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

Python uses Harbor's vendored upstream Pydantic models. TypeScript exports the
same wire shape, `parseTrajectory`, and `finalOutput` from `@agent-voyager-project/sdk/trajectory`.
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
retains typed final output, terminal reason, errors, observed timing,
cache-write/reasoning-token distinctions, citations, and provider annotations.
Unknown usage is omitted. Opaque child usage is counted only when individual
child responses are unavailable. Partial sums are calculated by readers from
recorded metrics; missing measurements remain unknown. Full tool metadata,
including titles, output schemas, MCP annotations, and server ownership, lives in
`inputs/effective-agent.json`; trace definitions use only standard ATIF fields.

Full configuration, complete skill directories, and generated files are preserved
as [run artifacts](../../spec/v0.1/artifacts.md). The manifest lists only path,
input/output role, and SHA-256. This keeps traces tight without dropping the
inputs needed for evaluation or recursive improvement. Native runtime event
archives are not required.

```python
from avp.artifacts import read_artifacts

manifest = read_artifacts(Path("."), run_id=trajectory.session_id)
for artifact in manifest.artifacts:
    print(artifact.role, artifact.path)
```

`read_artifacts` verifies every file and hash. TypeScript exposes the equivalent
`readArtifacts` from `@agent-voyager-project/sdk/artifacts`. Execution metadata
remains in ATIF, so reading the trace does not require separate detail files.
The manifest inventories captured files; it does not promise a full workspace or
a reproducible runtime environment.

## Verification and upstream updates

`make check` exercises shared Recorder fixtures, Python and TypeScript semantic
validation, and all eight adapter suites. It also checks that external Harbor
trajectories load without AVP extensions. Native CLI integration jobs and live
provider checks exercise runtime-specific behavior.

Upstream models and licenses live in `avp/_vendor/atif`. Run
`scripts/vendor-atif.py` with the pinned Harbor checkout, then `make schemas
bindings` when updating them. The upstream golden fixture and schema provenance
are documented in [`testdata/atif`](../testdata/atif/README.md).

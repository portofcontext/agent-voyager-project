# Run artifacts

A run can retain ordinary files beside its ATIF trajectory. `artifacts.json`
lists the captured files; it is not a second trace or a snapshot of the entire
environment. Storage, collection, and deduplication belong to the deployment.

```json
{
  "avp_version": "0.1",
  "run_id": "run-123",
  "artifacts": [
    {"path": "inputs/skills/research/SKILL.md", "role": "input", "sha256": "<64 lowercase hexadecimal characters>"},
    {"path": "outputs/report.md", "role": "output", "sha256": "<64 lowercase hexadecimal characters>"}
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `avp_version` | Yes | `0.1` |
| `run_id` | Yes | The run's identity, matching the ATIF `session_id` |
| `artifacts` | Yes | A list of captured files, with unique paths |
| `path` | Yes | A relative POSIX file path inside the run directory |
| `role` | Yes | `input` or `output` |
| `sha256` | Yes | SHA-256 of the exact saved bytes, in lowercase hexadecimal |

Paths MUST NOT be absolute, contain `.` or `..` segments, empty segments,
backslashes, colons, or control characters, or resolve outside the run directory.
Every listed file MUST accompany an exported run, and its hash MUST match.
Readers MUST reject missing files, invalid paths, and hash mismatches rather
than silently using different content.

Input snapshots MUST remain immutable. Changed files are recorded under separate
output paths. Skills MUST include their supporting files when captured, not just
`SKILL.md`. Capture records what was made available; it does not assert that the
agent used every file. Credentials MUST NOT be copied into artifacts.

Producers publish files before atomically replacing the manifest. A live run's
manifest may grow as output files become available. Published entries MUST NOT
be removed or reassigned to different bytes or roles. The manifest inventories
captured files only; absence does not establish that a file or capability never
existed. No lineage, artifact service, or custom content encoding is required.

## SDK conventions

File sinks write `artifacts.json` beside the requested trajectory file. Each run
uses its own directory. The SDK
records the validated Commission and Descriptor under `inputs/`, the effective
configuration in `inputs/effective-agent.json`, and full skill directories under
`inputs/skills/`. Effective configuration points at the captured skill files and
retains the full tool catalog, including titles, output schemas, MCP annotations,
and server ownership. The trace uses only standard ATIF tool-definition fields.
Media and explicitly reported output files are output artifacts. The returned
result stays in ATIF, using `extra.avp.output` only when it differs from the
final agent message; the SDK does not copy it into a file. Execution and response metadata stay in the ATIF trace, using
standard fields first and `extra.avp` where necessary. Only fields exposed by
the runtime are recorded. A skill with an advertised source that cannot be read is a capture
error; a metadata-only skill without a source is not claimed as captured. If a
runtime exposes only an instruction body, the SDK saves it as `instructions.md`
and records `instructions_path` without claiming a complete skill directory.
Skill directory capture rejects symbolic links.

The Recorder's artifact method accepts bytes and a role. It does not crawl the
workspace. Deployments choose additional input and output files to capture.
Stdout remains a standalone ATIF document; use file output to retain artifacts.

The [schema](artifacts.schema.json) is generated from `avp.artifacts`.

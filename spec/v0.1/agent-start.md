# Agent Start

**Status:** Draft

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are interpreted as
[BCP 14](https://www.rfc-editor.org/rfc/rfc8174) when capitalized.

Agent Start records the resolved configuration exposed by the runtime after
applying the Commission to the agent's capabilities and defaults.
It describes the start of execution; the ATIF trajectory records what follows.
The runtime still owns the merge, model calls, tools, and loop. The snapshot
records what the adapter can observe; it does not guarantee exact replay.

## Reference

| Field | Type | Required | Meaning |
|---|---|---|---|
| `avp_version` | string | Yes | `0.1`. |
| `run_id` | string | Yes | A nonempty run ID, matching the Commission when present and ATIF `session_id`. |
| `prompt` | string | Yes | The effective user prompt. |
| `system_prompt` | string | No | The effective system prompt, including an explicitly empty override. |
| `model` | ModelRef | Yes | Effective provider, model ID, and optional API base URL. No credential value. |
| `tools` | Tool[] | No | Full resolved tool definitions, including input/output schemas, MCP annotations, and server ownership. |
| `mcp_servers` | StartedMcpServer[] | No | Resolved server identities and status; connection configuration when available. |
| `skills` | StartedSkill[] | No | Selected skills, with paths to their captured files when available. |
| `subagents` | StartedSubagent[] | No | Selected subagent definitions, prompts, tools, servers, and captured skills. |
| `output_schema` | object | No | The requested structured-output schema. |

For `system_prompt`, `tools`, `mcp_servers`, `skills`, and `subagents`, absent and
`null` both mean not reported. An empty list means no items. An empty
`system_prompt` is an explicit empty prompt. These meanings also apply within
subagents, whose fields do not implicitly inherit from the parent. Producers
SHOULD omit unreported fields. Reused MCP and Descriptor fields retain their
own documented defaults.

`Tool`, skill metadata, and subagent metadata reuse the
[Descriptor](agent-descriptor.md). `ModelRef` is the Commission model without its
credential. A StartedMcpServer uses Descriptor server fields plus the Commission's
`http` or `stdio` connection fields when exposed. Secret references remain
references; resolved credential values MUST NOT be included. A server's absence
of connection fields means those internals were not exposed by the runtime.

A tool's optional `mcp_server_id` identifies its entry in `mcp_servers`. Native
tools omit it; MCP tools include it for both local and remote servers.

A StartedSkill adds `path`: a skill directory relative to `agent-start.json`.
Readers MUST resolve it within the saved run directory. Paths MUST use `/`
separators and MUST NOT be absolute or contain empty, `.` or `..` segments,
backslashes, colons, or control characters (U+0000–U+001F).

The SDK copies exposed skill files into that directory, preserving their bytes.
A complete skill includes `SKILL.md` and its supporting files. When only an
instruction body is exposed, the directory contains `instructions.md`; this
does not claim a complete skill. Absent or null `path` means no files were
captured. The inherited `source`, when present, is the original runtime location;
readers use `path` to access the saved copy.

A reported local source that cannot be captured is an error. Symlinks within
skill directories are rejected during capture. StartedSubagent uses the same
skill and server shapes for its nested lists. Capturing a skill records what
was available, not whether every file was used.

## Example

```json
{
  "avp_version": "0.1",
  "run_id": "example-run",
  "prompt": "Summarize the report",
  "model": {"provider": "anthropic", "id": "example-model"},
  "tools": [],
  "skills": [
    {
      "name": "summarize",
      "description": "Summarize reports",
      "path": "skills/0-summarize"
    }
  ]
}
```

This example has no tools and one captured skill. Its files are under
`skills/0-summarize/` beside `agent-start.json`. Omitted fields are not reported.

## Saved run

```text
run/
  commission.json
  descriptor.json
  agent-start.json
  trajectory.json
  skills/
    0-summarize/
      SKILL.md
      references/
        example.pdf
```

The SDK file sink saves these documents beside the requested trajectory path.
The Commission is absent for direct runs without one. Agent Start is written
once start succeeds, and is absent for a run refused before start. Readers must
validate Agent Start and its run identity before using it. The initial snapshot
does not change when the runtime switches models later; the trace records that.

Skill files are saved before Agent Start publishes their paths. Copies are
immutable start snapshots, independent of the runtime's temporary directories.
The SDK uses separate directories for root and subagent skills; directory names
are a storage convention, and readers MUST follow the recorded `path`.

Keep or move the saved run directory as a unit, including referenced skill and
image files. These references need no separate manifest or base64 encoding.
Commission and Descriptor remain unchanged source contracts; a Commission still
carries supplied skill text inline. Their overlap with the resolved snapshot lets
a reader compare requested, offered, and effective configuration.

Generated files can be saved beside the run by the runtime or deployment.
ATIF-referenced image files are written by the SDK. Stdout emits only the ATIF
document; use file output to retain the other documents and captured skill files.

The [schema](agent-start.schema.json) is generated from `avp.agent_start`.

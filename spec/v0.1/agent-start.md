# Agent Start

**Status:** Draft

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are interpreted as
[BCP 14](https://www.rfc-editor.org/rfc/rfc8174) when capitalized.

Agent Start records the configuration the runtime reports after applying the
Commission and its own defaults. The ATIF trajectory records what happens next.
The runtime handles setup, model calls, tools, and the loop. Agent Start saves
what the adapter can observe; it doesn't guarantee that a run can be replayed exactly.

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
subagents, whose missing fields do not inherit values from the parent. Agents
SHOULD omit fields they cannot report. MCP and Descriptor fields keep their
own documented defaults.

`Tool`, skill metadata, and subagent metadata reuse the
[Descriptor](agent-descriptor.md). `ModelRef` is the Commission model without its
credential. A StartedMcpServer uses Descriptor server fields and adds the
Commission's `http` or `stdio` connection fields when available. Secrets MUST
remain references, without their actual values. Missing connection fields mean
the runtime did not report them.

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

If the runtime reports a local skill directory, the SDK must be able to read it.
The SDK rejects symlinks inside skill directories. StartedSubagent uses the same
skill and server fields. Saving a skill shows what was available; it doesn't
mean the agent read every file.

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

The SDK saves skill files before writing Agent Start with their paths. These
copies stay unchanged even if the runtime edits or removes the original files.
The SDK uses separate directories for root and subagent skills; directory names
are a storage convention, and readers MUST follow the recorded `path`.

Keep or move the saved run directory as a unit, including referenced skill and
image files. These references need no separate manifest or base64 encoding.
Commission still includes supplied skill text inline. Saving Commission,
Descriptor, and Agent Start lets you compare what was requested, what the agent
offered, and what it actually configured.

Generated files can be saved beside the run by the runtime or deployment.
The SDK saves image files referenced by ATIF. Stdout contains only the ATIF
document; use file output to retain the other documents and captured skill files.

The [schema](agent-start.schema.json) is generated from `avp.agent_start`.

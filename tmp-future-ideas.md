# Future ideas

Improvements to consider after the v0.1 cleanup. Not decided; nothing here is
in the specs yet.

## Open Responses migration

Move the Trajectory's content blocks to [Open Responses](https://www.openresponses.org/specification)
items, the model-call format now governed by the AAIF. Tracked in
[#75](https://github.com/portofcontext/agent-voyager-project/issues/75).
Open Responses covers only model-call items (messages, tool calls,
reasoning), so the rest of the Trajectory stays AVP's own.

- Why: AVP keeps its own block set
  ([Content blocks](avp/core/spec/v0.1/trajectory.md#313-content-blocks)) for
  a problem Open Responses solves under neutral governance.
- To work out:
  - The mapping from each AVP block to an Open Responses item, and which
    blocks have no equivalent.
  - Citations: AVP's [Citation](avp/core/spec/v0.1/trajectory.md#3131-citation)
    maps to a `url_citation` annotation (`source_url` to `url`,
    `source_title` to `title`, `start_index` and `end_index` unchanged). Open
    Responses has no `cited_text`, `source_id`, or file and document
    citations; decide whether AVP extends the annotation with them.

## Connection details on Descriptor MCP servers

Add the server's connection details to the Descriptor's MCP server entry
(the Descriptor's [MCP server](avp/core/spec/v0.1/agent-descriptor.md#33-mcp-server)): the URL for an HTTP server, or the command
and arguments for a stdio server. Never credentials.

- Why: a reviewer could see exactly which server the agent talked to, not just
  an `id`. It would also bring the Descriptor's entry closer to the
  Commission's `McpServerHttp` / `McpServerStdio`, possibly one shape for both
  with secret header values left out.
- To work out:
  - Headers and `env` values often hold secrets in an agent's own config.
    Either leave them out entirely or define which keys are safe.
  - Some SDKs report servers without their connection details (for example
    Claude Agent SDK's account-level servers). The fields would have to be
    optional.
  - Stdio commands can contain host paths, the same concern as Skill `source`.

## References or `inherit` instead of repeated items

Today a subagent that shares the agent's tools, MCP servers, or skills lists
them again in full (the Descriptor's [Subagent](avp/core/spec/v0.1/agent-descriptor.md#35-subagent)). Consider a way to point
at the agent's items instead.

- Options:
  - An `inherit` keyword in place of a list, meaning "the same as the agent".
  - References by name or `id` to entries in the agent's lists, so a subagent
    can take a subset without repeating each Tool object.
- Why: Descriptors with large tool catalogs repeat every Tool, schemas
  included, once per subagent.
- To work out:
  - A field typed "list or keyword" or "object or reference" makes every
    supervisor resolve it before reading; decide whether the size saving is
    worth that.
  - One reference style for the whole spec, not one per field. The same
    question comes up for the Commission and Trajectory (for example
    `agent_started` repeating the Descriptor's lists).
  - What a reference means in the copy produced before a run, when
    MCP-provided tools are not known yet.

## Default prompt on the Descriptor

Bring back a Descriptor `prompt`: the default user prompt for an agent that
does a fixed job on its own, for example a helpdesk agent that a scheduler
runs every morning with a Commission that has no `prompt`. A Commission's
`prompt` would replace it. Removed in the cleanup (C5) because no agent set it.

- To work out:
  - What happens when neither the Commission nor the Descriptor has a prompt:
    the agent fails with an error, or starts with no user message.
  - Whether the default belongs on the Descriptor, or on a saved Commission
    the scheduler reuses.

## Version ranges in a Commission's agent `version`

Let `agents.<name>.version` accept a range such as `^1.2.3`, not only an exact
version. Today it is an exact string match (C20).

- Why: a Commission could accept compatible releases without being rewritten
  for each one.
- To work out:
  - `agent_version` has no defined format. Ranges need it to be semver.
  - One named range syntax for every binding; npm, Cargo, and Python read
    `^` and `~` differently.
  - A range accepts the behavior changes a pin is meant to catch. Leaving
    `version` out already means "any version".

## Patterns in `agents` keys

Let a key in a Commission's `agents` map be a pattern, so one entry applies to
several agents: `"acme-*"` matches `acme-code-agent` and `acme-review-agent`. Today each key is an exact `agent_name`
(C20).

- Why: one Commission can set the same tool list or pin for a family of
  agents without repeating the entry.
- To work out:
  - Use the same pattern syntax as the Descriptor's `supported_models`
    (`*` matches any characters), not a second syntax.
  - Which entry wins when several keys match the running agent: the exact
    name first, then the longest pattern, or refuse as ambiguous.
  - Whether the refusal rule still holds: `agents` present with no exact or
    pattern match for the running agent means the agent refuses.
  - Patterns in the `enabled_*` lists too (for example every tool from one
    MCP server), with the same syntax.
  - `agent_name` already excludes `*` (C22), so adding patterns later breaks
    nothing.

## Skill file paths that leave the skill directory

Require the agent to refuse a Commission Skill whose `files` key is absolute or
resolves outside the skill directory (for example `../../.bashrc`). Today the
spec says only that keys are relative paths.

- Why: a Commission could make the agent write files outside the skill
  directory. Low risk while the supervisor writes the Commission and the
  agent runs in a sandbox the launcher controls.
- To work out:
  - Add it as an `invalid_commission` case in the Commission's
    [checks before the run](avp/core/spec/v0.1/commission.md#51-the-agent-checks-the-commission-before-the-run-starts),
    or as a schema pattern on the keys.
  - Symlinks inside the skill directory.

## Mapping pages for outside formats

Add pages that convert a Trajectory to outside formats, under
`avp/core/spec/v0.1/mappings/`. They are separate from the specs, so changes in
those formats (the GenAI conventions are still experimental) don't need a new
AVP version.

- `cloudevents.md` (C35): AVP event to CloudEvent, for supervisors that
  forward Trajectories to brokers. `type` gets a prefix (`avp.tool_invoked`,
  or a reverse-DNS name), the forwarder sets `source`, `subject` comes from
  `run_id`, and `id`, `time`, and `data` carry over. The bindings implement it
  as a converter, for example `avp.cloudevents.to_cloudevent(event, source=...)`
  in Python with Rust and TS ports.
- `opentelemetry.md` (C34): AVP events to OpenTelemetry spans with GenAI
  attributes.
  - Spans: the run from `agent_started` to `agent_stopped` (GenAI agent span);
    each `assistant_message`, starting at `time` minus `duration_ms` (model
    call span); each tool call from `tool_invoked` to `tool_returned`; each
    subagent from `subagent_invoked` to `subagent_returned`.
  - Parents: a response under the run, or under its subagent; a call under the
    response whose `content` has its `tool_use`.
  - IDs: the trace ID from `run_id`; span IDs by hashing `run_id` with
    `tool_call_id` or `subagent_invocation_id`, so a conversion always gives
    the same IDs.
  - Joining an outside trace (the supervisor's, or spans the agent's framework
    emits): the converter takes a parent span, and the launcher passes a W3C
    `traceparent` to the agent process (for example the `TRACEPARENT`
    environment variable). Add an optional `traceparent` on `run_requested`
    only if a supervisor needs it in the Trajectory.
  - `gen_ai.py` already maps fields to attributes; still missing are the span
    building above and an exporter.

## Non-text data across AVP

AVP is built around text. Decide how each spec handles images, audio, video,
and other files, once an agent needs them (C46, C51).

- Commission: `prompt` is a string, so a run can't start from an image or a
  file. Skill `files` is `map<string, string>`, so a skill can't ship a binary
  file (an image, a font, a compiled script).
- Trajectory content: the only non-text block is `image`, always inline
  base64 (C51 removed `audio`, `video`, `document`, and URL and file-ID
  sources), and tool results can hold images. Not decided: whether large media
  goes inline as base64 (large events, secrets or personal data in the record)
  or by reference, and how a supervisor fetches a referenced file after the
  run.
- Usage and cost: services count and price audio, image, and video tokens
  separately (OpenAI `prompt_tokens_details.audio_tokens` and
  `completion_tokens_details.audio_tokens`; Gemini `promptTokensDetails` by
  modality). Usage has no field for them, so a cost computed from
  `input_tokens` and `output_tokens` alone can be wrong for these runs.
- Descriptor: whether a tool or model declares which kinds of input and output
  it accepts.

## Skill loads in the Trajectory

Record when the agent loads a skill. Today no event does, so a supervisor
can't tell which of `agent_started`'s `skills` the run used, or when.

- Why: a load shows up only as an ordinary tool call or file read, if at all,
  and each runtime does it differently: Claude's `Skill` tool, Goose's
  `load_skill` tool (`agents/avp-goose/rust/src/runner.rs:719`), or a plain
  read of `SKILL.md` by an agent without a skill tool.
- To work out:
  - A `skill_loaded` event, or a field on `tool_invoked`.
  - How an agent detects a load it doesn't make through a tool.
  - Whether loading one of a skill's other files counts.

## Turning off single tools of a built-in MCP server

Let a Commission turn off some tools of a built-in MCP server and keep others
(Q2). In v0.1, `enabled_tools` covers only tools without `mcp_server_id`, and
a built-in server's tools are all on or all off through `enabled_mcp_servers`.

- To work out:
  - Let `enabled_tools` name MCP tools too, usable only when both lists allow
    them.
  - The unknown-name check can't be strict for them, because a server's tools
    change between runs (the Descriptor rule on MCP tools).
  - Which runtimes can hide one tool of a server.

## Agent settings and a subagent's own items

Decide whether a name missing from `enabled_tools` (or the other lists) also
turns the item off where it appears in a subagent's own lists (Q5). v0.1
doesn't say.

- Why: without it, a Commission without `WebFetch` doesn't stop a subagent
  that has `WebFetch`, so a "no network" Commission doesn't hold. Turning the
  subagent off with `enabled_subagents` does.
- Options:
  - Lists cover top-level items only.
  - A name turns the item off wherever it appears; the unknown-name check then
    accepts names from subagents' lists.
  - Per-subagent settings in the agent's entry.
- To work out: which runtimes can filter a subagent's tools separately from
  the parent's.

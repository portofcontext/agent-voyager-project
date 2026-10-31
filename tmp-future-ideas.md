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
  ([Content blocks](spec/v0.1/trajectory.md#313-content-blocks)) for
  a problem Open Responses solves under neutral governance.
- To work out:
  - The mapping from each AVP block to an Open Responses item, and which
    blocks have no equivalent.
  - Citations: AVP's [Citation](spec/v0.1/trajectory.md#3131-citation)
    maps to a `url_citation` annotation (`source_url` to `url`,
    `source_title` to `title`, `start_index` and `end_index` unchanged). Open
    Responses has no `cited_text`, `source_id`, or file and document
    citations; decide whether AVP extends the annotation with them.

## Converting message histories

Add SDK functions that convert between AVP's conversation and the message
history formats agents and model services use, such as Anthropic Messages,
OpenAI Chat Completions, and OpenAI Responses. AVP's format is its own content
blocks for now, and Open Responses items after the
[Open Responses migration](#open-responses-migration).

- Why: every agent converts its runtime's messages into AVP content blocks,
  and every supervisor that replays or exports a run converts them back. Shared
  converters would make each format map the same way in every agent and SDK.
- To work out:
  - Which formats to support first, and in which directions: into AVP for
    agents, out of AVP for supervisors.
  - Rebuilding the conversation from a Trajectory: one conversation per
    `subagent_invocation_id`, not one mixed list. The old `avp.history` didn't
    separate them.
  - Blocks one format has and another lacks, such as `server_tool_result` or
    `thinking` signatures.

## Transport

Define how a Commission reaches the agent and how its events come back. The
specs leave this out today, and the SDKs carry a provisional file transport
outside the spec (`avp.agent_cli`: `ping`, `describe`, and `run --commission --out`
with NDJSON) so agents can be run, demoed, and checked by `avp conformance`.

- Why: every supervisor that starts agents needs the same contract, and today
  that contract lives only in the SDK and avp-cli.
- To work out:
  - Which transports to define: a subprocess with files or stdio, HTTP, or
    both.
  - Whether the spec defines the command line itself, or only what a
    transport must carry.
  - Interruption: how a supervisor asks a running agent to stop.

## Connection details on Descriptor MCP servers

Add the server's connection details to the Descriptor's MCP server entry
(the Descriptor's [MCP server](spec/v0.1/agent-descriptor.md#33-mcp-server)): the URL for an HTTP server, or the command
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
them again in full (the Descriptor's [Subagent](spec/v0.1/agent-descriptor.md#35-subagent)). Consider a way to point
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
    [checks before the run](spec/v0.1/commission.md#51-the-agent-checks-the-commission-before-the-run-starts),
    or as a schema pattern on the keys.
  - Symlinks inside the skill directory.

## Mapping pages for outside formats

Add pages under `spec/v0.1/mappings/` that describe how a Trajectory converts
to CloudEvents and to OpenTelemetry spans. The SDK already does both
(`avp.utils.cloudevents`, `avp.utils.otel`); the pages would let other
implementations convert the same way without reading the SDK. They stay
separate from the specs, so changes in those formats don't need a new AVP
version.

- To work out:
  - Whether the SDK's mapping becomes the pages' content, or the pages come
    first and the SDKs follow them.
  - The GenAI conventions moved to
    [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai),
    are in Development, and have no release yet. Decide which revision to
    follow until they have one.
  - `gen_ai.input.messages` and `gen_ai.output.messages` need AVP blocks
    converted to OpenTelemetry message parts. See
    [Converting message histories](#converting-message-histories).

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

## Equivalent models across services

Help supervisors find the same model at other services when writing a
Commission. models.dev links each service's entry to the maker's model with
`canonical_model_id`, so `anthropic/claude-sonnet-5-5` maps to
`claude-sonnet-5-5` at `anthropic`, `anthropic/claude-sonnet-5.5` at
`openrouter`, and `claude-sonnet-5-5@default` at `google-vertex`.

- Why: comparing a model across services, or switching services, means looking
  up a different `id` for each one.
- To work out:
  - Some services list one model under several IDs (Bedrock's `us.`, `eu.`,
    and `global.` profiles), so a lookup can return more than one.
  - About 15% of models.dev entries have no `canonical_model_id`.
  - Whether this belongs in the CLI or a shared library rather than the spec.

## Model credentials beyond a single key

A Model's `credential` is one Secret reference: one static secret, from a proxy
or an environment variable. Running Claude at four services shows where that
falls short:

| Service | How it authenticates | Fits one Secret reference |
|---|---|---|
| Anthropic | A static API key in `x-api-key` | Yes |
| OpenRouter | A static key in `Authorization: Bearer` | Yes |
| Bedrock, API key | `AWS_BEARER_TOKEN_BEDROCK` as a bearer token. Short-term keys expire within 12 hours; long-term keys belong to an IAM user | Yes, if the key outlasts the run |
| Bedrock, IAM | Each request is signed (SigV4) with an access key ID, a secret key, an optional session token, and a region | No: two or three secrets, and a proxy must re-sign the request rather than add a header |
| Bedrock, role or SSO | Credentials come from the machine's role, SSO, or a profile | Nothing to name |
| Vertex | A Google OAuth access token in `Authorization: Bearer`, valid for about an hour, minted from a service account key file or the machine's default credentials | No: a token expires during a long run, and the key is a file, not a value |

- Why: the usual ways to run Claude on Bedrock and Vertex can only be expressed
  by leaving `credential` absent, so the Commission can't say which credential
  a run uses there.
- To work out:
  - `{ "proxy": ... }` names a credential only the proxy's setup uses; the
    agent never reads it. Signed or minted credentials need a proxy that
    signs or mints, not one that adds a header.
  - `{ "env": ... }` names one variable, not the several AWS values or a key
    file.
  - Bedrock's region and Vertex's project and location fit in `base_url`, but
    the Bedrock and Vertex SDKs take them as separate settings.

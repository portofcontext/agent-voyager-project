# AVP connector for Goose (Rust, in-process) — design

Status: live in-process path implemented and conformant except live usage.
`commission.rs` maps a Commission to Goose `Agent` config; `runner.rs` drives
`Agent::reply()`, emits the prelude (`run_requested` + `agent_described` from
`Agent::list_tools()`), streams events into the emitter, and infers the stop
reason (`classify_stop`). `avp-goose-run` runs a Commission and emits NDJSON;
a live run produces the full ordered trajectory with real usage/cost. Shared
test harness (`tests/common`) with schema-conformance baked in; 32 tests / 3
ignored (band 2 subagent + MCP-lifecycle specs).


## 1. Decision

Build the Goose AVP connector as an **in-process Rust observer of Goose's
internal `AgentEvent` stream**, and upstream it into the Goose tree as a
first-class, opt-in trajectory emitter.

Why in-process Rust rather than an external wrapper over ACP or goosed
REST+SSE (the prior options we weighed):

- The installed CLI ships only ACP (`goose acp` stdio, `goose serve`
  HTTP/WS); the goosed 103-endpoint REST+SSE surface is desktop-only.
- ACP omits in-band token usage; goosed's SSE carried it. In-process we
  read `ProviderUsage` straight off the loop, so usage/cost is recovered
  at the source.
- Upstreaming removes the "unstable internal API" objection: we move with
  Goose and their CI guards breakage. Block already ships features to
  Goose, so the merge path is real.
- We need Rust AVP agents eventually anyway. Goose is a good first one: it
  forces the reusable Rust agent base into existence (see §4).

The connector sits as a **sibling of the existing ACP server**
(`crates/goose/src/acp/server.rs`), which already consumes the same
`AgentEvent` stream and translates it to a wire protocol. We are adding a
second translator, not a new integration point.

## 2. The Goose seam (verified against current source)

| Concern | Goose API | Location |
|---|---|---|
| Run a turn, get an event stream | `Agent::reply(user_message, session_config, cancel_token) -> BoxStream<Result<AgentEvent>>` | `crates/goose/src/agents/agent.rs:1352` |
| Internal event enum | `enum AgentEvent { Message(Message), McpNotification((String, ServerNotification)), HistoryReplaced(Conversation) }` | `agent.rs:221` |
| Content variants | `enum MessageContent`: `Text, Image, ToolRequest, ToolResponse, ToolConfirmationRequest, FrontendToolRequest, Thinking, RedactedThinking` (serde `tag="type"`, camelCase) | `crates/goose/src/conversation/message.rs` |
| Per-turn usage | `ProviderUsage { model, usage: Usage { input_tokens, output_tokens, total_tokens, cache_read_input_tokens, cache_write_input_tokens } }` on the provider `MessageStream` | `crates/goose/src/providers/base.rs:676,715` |
| Tool request | `ToolRequest { id, tool_call: ToolResult<CallToolRequestParams { name, arguments }> }` | `message.rs:78` |
| Tool response | `ToolResponse { id, tool_result: ToolResult<CallToolResult { content, is_error }> }` | `message.rs:173` |
| Tool catalog with schemas | `Agent::list_tools(session_id, cursor) -> Vec<rmcp::model::Tool { name, description, input_schema }>` | `agent.rs:1255` |
| Extension config | `enum ExtensionConfig { Stdio, Builtin, Platform, StreamableHttp, Sse, Frontend, InlinePython }` (each carries name/description) | `crates/goose/src/agents/extension.rs:153` |
| Subagent execution | `run_subagent_task(SubagentRunParams)` creates a child `Agent`, calls `reply()`, streams child activity back via `notification_tx` | `crates/goose/src/agents/subagent_handler.rs:48` |
| ACP translator (our blueprint) | `on_initialize`, `on_new_session`, dispatch | `crates/goose/src/acp/server.rs:2483,2525` |

Three facts shape the mapping:

1. **All richness lives inside `Message.content`.** `AgentEvent` itself is
   trivial (3 variants). Tools, thinking, and text are `MessageContent`
   items, so the translator is a straightforward per-item projection.
2. **No internal stop-reason enum.** The loop just ends when a response has
   no tool requests; `reply.rs` hardcodes `"stop"`. AVP `StopReason` must be
   inferred (see §6).
3. **No first-class subagent or MCP-lifecycle events.** Subagents run as a
   `summon` tool call; the child surfaces via `McpNotification`. Extension
   connect/disconnect is not on the stream. Both are synthesized (§6, §7).

## 3. Architecture

```
Commission (stdin / supervisor)
        │
        ▼
  commission.rs  ── maps Commission → Goose AgentConfig + SessionConfig + ExtensionConfig[]
        │
        ▼
  AvpGooseRunner (runner.rs)
   ├─ build descriptor via Agent::list_tools() + ExtensionConfig set   → agent_described
   ├─ emit run_requested, agent_started (prelude, before reply)
   ├─ Agent::reply(...) -> BoxStream<AgentEvent>
   │      └─ for each AgentEvent: translate.rs + runstate.rs (turn buffer)
   │             └─ emit assistant_message / tool_invoked / tool_returned / subagent_* via Sink
   └─ on stream end / error / cancel: emit agent_stopped
        │
        ▼
   Sink (avp base): StdioSink (NDJSON) | OtlpSink | FileSink | WsSink
```

Transport is a `Sink` choice, not a protocol. Non-stdio output (the
original ask) is just a different `Sink` impl; nothing else changes.

## 4. The Rust AVP agent base (what to add to `avp/bindings/rust/`)

`avp/bindings/rust/` today is **wire types only**, generated from the schemas
(`trajectory.rs`, `commission.rs`, `agent_descriptor.rs`). Every event type
we need already exists: `RunRequestedEvent`, `AgentDescribedEvent`,
`AgentStartedEvent`, `AssistantMessageEvent`, `ToolInvokedEvent`,
`ToolReturnedEvent`, `SubagentInvoked/Returned/FailedEvent`, `SubagentUsage`,
`AgentStoppedEvent`, `ErrorOccurredEvent`, the `AvpV01TrajectoryEvent` union,
and the `StopReason` / `ErrorCode` / cost-source / dispatch-target enums.

Missing is the agent-base machinery that Python keeps in `avp/`. Port these
(small, reusable across every future Rust agent):

| Python source | Rust addition | Contents | Status |
|---|---|---|---|
| `avp/envelope.py` | `avp/bindings/rust/src/ids.rs` | `now_iso`, `new_event_id`, `new_trace_id`, `new_span_id`, `ZERO_SPAN_ID`, `SOURCE_AGENT` (uuid `v4` + chrono `clock` features) | done |
| `avp/sink.py` | `avp/bindings/rust/src/sink.rs` | `trait Sink { fn emit(&self, &Event) -> io::Result<()> }` + `StdioSink` (NDJSON). Sync + object-safe; sinks needing async/state use interior mutability | done |
| `avp/pricing.py` + `avp/data/prices.json` | `avp/bindings/rust/src/pricing.rs` | `ModelPrice`, `CostSource` (re-exported wire enum), `compute_cost`, `load_default_prices`; default table shared with Python via `include_str!` (one source of truth) | done |

This base is the deliverable that outlives Goose. The connector itself
(§5) is the integrator package and stays Goose-specific.

Built flat (`ids`/`pricing`/`sink` at the crate root) rather than under an
`agent/` module: there is no shared agent base class in any binding (each
agent inlines its own loop), so the extra nesting would be structure for a
hypothetical caller. `cargo test` green (8 base unit
tests + 3 roundtrip). The `prices.json` `include_str!` reaches into the Python
package data file; publishing the `avp` crate standalone (§12) will swap that
for a build-script copy of the same file.

## 5. Connector module map

| Module | Role |
|---|---|
| `runner.rs` | Owns the `Agent`, builds the descriptor, emits the prelude, drives `reply()`, emits stop |
| `translate.rs` | `MessageContent` → AVP content blocks; `Tool` / `ExtensionConfig` → `*Decl` |
| `emit.rs` | Per-`AgentEvent` dispatch; constructs lifecycle + tool + subagent events |
| `runstate.rs` | Turn buffering; one `assistant_message` then buffered tool/subagent events |
| `events.rs` | Event constructors hiding the CloudEvents envelope + validated newtypes |
| `commission.rs` | Commission → Goose config |

## 6. Event mapping: `AgentEvent` → AVP trajectory

Prelude (emitted by `runner.rs` before `reply()`):
`run_requested` → `agent_described` → `agent_started`.

Per-turn translation buffers like `RunState.drain()`: accumulate `Text` /
`Thinking` content into the open turn, flush a single `AssistantMessageEvent`
plus its buffered tool/subagent events at each turn boundary.

| Goose | AVP event | Notes |
|---|---|---|
| `AgentEvent::Message` with `Text` | accumulate → `AssistantMessageEvent` (`TextBlock`) | |
| `Message` with `Thinking` / `RedactedThinking` | `ThinkingBlock` on the assistant message | `redacted` flag set for the latter |
| `Message` with `ToolRequest` | `ToolInvokedEvent` | `id`→`tool_call_id`; `tool_call.name`→`tool_name`; `arguments`→`tool_input`; dispatch target per §7 |
| `Message` with `ToolResponse` | `ToolReturnedEvent` | `tool_result.content`→`tool_result`; `is_error`→`is_error`; pair to the request by `id` |
| `ToolRequest` whose tool is `summon`/subagent | `SubagentInvokedEvent` then `SubagentReturnedEvent` | Synthesized around the summon tool call; child usage (if recoverable) → `SubagentUsage` on returned (AVP's documented in-process black-box fallback) |
| `AgentEvent::McpNotification` | `avp.meta` on the current event, or drop | Child-subagent activity and MCP server logging arrive here |
| `AgentEvent::HistoryReplaced` | drop | Compaction/clear; reconstructable, not on the wire |
| `ProviderUsage` per turn | `usage` + `cost_usd` + `cost_source` on `AssistantMessageEvent` | `compute_cost` from base pricing; `response_model` from `ProviderUsage.model` |
| stream ends cleanly | `AgentStoppedEvent { reason: Converged }` | |
| stream yields `Err` | `ErrorOccurredEvent` then `AgentStoppedEvent { reason: Error }` | map provider error → `ErrorCode` where possible |
| `cancel_token` cancelled | `AgentStoppedEvent { reason: Interrupted }` | |
| refusal detected in content | `AgentStoppedEvent { reason: Refused }` | best-effort; Goose has no explicit refusal signal |

## 7. Descriptor sourcing (in-process, no probe)

In-process we call the live registry directly, so the descriptor needs no
throwaway probe session.

| `AgentDescriptor` field | Source |
|---|---|
| `agent_name` / `agent_version` | `"goose"` + crate version (or ACP `agentInfo`) |
| `default_model` | session provider/model config (`GOOSE_MODEL`) |
| `tools[]` with `inputSchema` | `Agent::list_tools(session_id, None)` → `rmcp::Tool` → `ToolDecl` |
| `mcp_servers[]` (`McpServerDecl`) | `ExtensionConfig::{Stdio, StreamableHttp, Sse}` entries |
| `subagents[]` (`SubagentDecl`) | the `summon` extension's recipes/subagents |
| `skills[]` (`SkillDecl`) | `skills::discover_skills()` → `SourceEntry` |
| `capabilities[]` | ACP `agentCapabilities` |

`tool_dispatch_target` per tool: `mcp_server` when the tool's owning
extension is `Stdio`/`StreamableHttp`/`Sse`; `local` for
`Builtin`/`Platform`/`Frontend`/`InlinePython`. Goose namespaces tools as
`{extension}__{tool}`, so the prefix identifies the owner.

## 8. Commission → Goose config

Maps Commission fields onto Goose config types.

| Commission field | Goose target |
|---|---|
| `model` | session provider/model config |
| `system_prompt` | agent system prompt |
| `prompt` | the `user_message` passed to `reply()` |
| `enabled_builtin_tools` | builtin extension enable set (cf. `--with-builtin`); `None`=all, `[]`=none, `[...]`=subset |
| `mcp_servers` (inline http/stdio) | `ExtensionConfig::StreamableHttp` / `ExtensionConfig::Stdio` |
| `skills` (inline) | written to a skills dir discoverable by `discover_skills()` |
| `output_schema` | final-output tool / structured-output config |
| `run_id` / `supervisor` / `thread_id` / `tags` / `meta` | AVP-only; stamped on `run_requested` / `agent_started` |

## 9. Design simplifications (in-process)

Observing Goose in-process keeps the connector small:

- **No probe session.** `Agent::list_tools()` returns tool schemas directly,
  so the descriptor needs no throwaway session.
- **No ambient run state.** `RunState` is threaded explicitly.
- **Usage is first-class and per-turn.** `ProviderUsage` arrives on the
  stream, so there is no reconstructing cumulative usage from message classes.
- **One clean stream.** The connector consumes `BoxStream<AgentEvent>`
  directly rather than teeing a client's message iterator.

## 10. Remaining fidelity gaps (and how we handle them)

- **Stop reason.** Goose models only "ended". We infer `Converged` (clean
  end), `Error` (stream error), `Interrupted` (cancel), `Refused`
  (best-effort content scan). Documented; not a blocker for conformance.
- **Subagent granularity.** `summon` is a tool call; the child is a separate
  `Agent` whose per-turn events do not surface on the parent stream (only
  `McpNotification` summaries). We emit `subagent_invoked`/`returned` around
  the tool call with `SubagentUsage` when recoverable. This is exactly the
  AVP-documented black-box fallback, so the wire stays conformant.

## 11. Cross-check notes

- **Bindings regenerated (done).** The committed Rust + TS bindings had
  drifted from the schemas on this branch (stale resolver-era types). Ran
  `make schemas` + `make bindings`; now drift-clean (`make bindings-check`
  passes). Also fixed stale hand-written resolver docs in `rust/avp/src/lib.rs`
  and `typescript/avp/src/index.ts`, and modernized `rust/avp/tests/roundtrip.rs`
  off the pre-v0.1 event types onto current ones (`assistant_message`,
  `agent_stopped reason=refused`).
- **Trajectory union discrimination (fixed).** typify ignored the schema's
  OpenAPI `discriminator` and emitted `#[serde(untagged)]` for the `type`-
  discriminated Rust unions (trajectory Event, content blocks, Commission
  `mcp_servers`), so they matched by first structural fit (an
  `avp.agent_started` event deserialized as `RunRequestedEvent`). Fixed with
  a post-process step, `scripts/tag-rust-unions.py`, wired into
  `generate-bindings.sh`: it rewrites those unions to `#[serde(tag = "type")]`,
  adds per-variant `#[serde(rename = "avp.*")]` from the schema's const tags,
  and `skip_serializing`s each member struct's `type_` field so the tag is not
  emitted twice. Canonical schema untouched (Rust-only; TS already
  discriminated). Rust + TS roundtrip tests modernized off removed event types
  and green; `make bindings-check` drift-clean.
- **Done (Python side):** the stale post-resolver-removal conformance cases were
  removed; the live suite at `avp/core/conformance/src/avp_conformance/cases/v0.1/`
  has no resolver cases (see its `COVERAGE.md`).
- **Conformance.** The connector is validated the same way as the Python
  agents: replay real Goose content through `translate.rs` + `runstate.rs`,
  validate emitted events against `spec/v0.1/trajectory.schema.json`, run
  `avp-conformance`. Fixture-driven translation stays deterministic and free;
  live Goose runs are the paid smoke layer.
- **Free fixture source (validated).** Goose persists every message's content
  to `~/.local/share/goose/sessions/sessions.db` (`messages.content_json`),
  verbatim in the `MessageContent` wire form. `translate.rs` is golden-tested
  against real records pulled from there (`tests/golden.rs`), so no paid run is
  needed to validate input shapes. This caught two real wire facts the
  source-only reading missed: tool fields are `toolCall` / `toolResult`
  (camelCase, not `tool_call`), and the dispatching extension is in
  `_meta.goose_extension` (older messages omit it; the `{ext}__{tool}` name
  prefix is the fallback). `arguments` may be absent; `signature` may be empty.
- **Full-pipeline golden (validated).** `tests/pipeline.rs` drives a verbatim
  5-message session round (`fixtures/real_session_round.json`) through
  `translate -> runstate -> emit` and asserts the emitted trajectory. Confirmed
  a real pattern: Goose splits an assistant turn's text and its tool call into
  separate messages (so each maps to its own `assistant_message` step), and the
  matching `tool_returned` arrives in a later message and pairs back to the
  invocation by tool-call id across the message boundary. Every emitted event
  re-discriminates as a typed `Event`.
- **Source-of-truth rule holds.** The canonical spec schemas remain
  authoritative; the Rust agent base consumes generated types and adds only
  runtime machinery, never new wire shapes.

## 12. Open questions for upstreaming

1. **AVP crate distribution.** For Goose to depend on AVP in-tree, the
   `avp` crate (types + base) must be published to crates.io or vendored.
   Recommend publishing; keep drift detection in the AVP repo.
2. **Integration point + flag.** Land as an opt-in observer behind a feature
   flag (e.g. a `--avp` sink on `goose acp`/`serve`, or an `AVP_TRAJECTORY`
   env). Keep it off the hot path so maintainers accept it.
3. **Crate home.** Decide whether the connector lives in this repo
   (`rust/avp-goose/`) and is mirrored into Goose, or lives in the Goose tree
   depending on the published `avp` crate. Upstream-first argues for the
   latter once the `avp` crate is published.

## 13. Build plan

1. Regenerate `rust/avp` bindings; confirm drift-clean.
2. Add the Rust agent base to `rust/avp` (§4): `ids.rs`, `agent/sink.rs`,
   `pricing.rs`. Unit-test `compute_cost` against the Python `pricing` cases.
3. Scaffold the connector (§5) with `translate.rs` first, TDD against
   captured `AgentEvent` fixtures.
4. Wire `runner.rs` to a real `Agent`; emit to `StdioSink`.
5. Conformance pass; then a paid live smoke on a cheap model.
6. Maintainer conversation on §12 before opening the upstream PR.

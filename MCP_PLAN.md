# MCP wire-shape change: drop connect/disconnect events

## Why

- **Agent loops rarely expose connect/disconnect hooks.** SDKs that black-box the MCP client (Claude Agent SDK, raw Anthropic + ad-hoc MCP) can't reliably emit these events; current spec forces a stub-event escape hatch that carries `null` for the load-bearing fields.
- **Two wire surfaces already enumerate "what tools exist."** `agent_described` is the agent's manifest; `agent_started` is the merged runtime snapshot. A per-server lifecycle event is a third surface that duplicates the first two.
- **Today's spec contradicts itself.** trajectory.md §2.1 says MCP-surfaced tools live ONLY on `mcp_server_connected`; agent-descriptor.md §3 (lines 197, 216) says they live on `agent_started.data["avp.tools"]` and `mcp_server_connected`. Removing the event forces one source of truth.
- **Disconnects are derivable from run-end.** No consumer needs a per-server close signal that isn't already implied by `agent_stopped`.
- **Failures deserve a louder signal than a status enum.** A failed dial belongs in `error_occurred`, not buried in `mcp_server_connected.data["avp.mcp.status"]: "failed"`.

## Design

- **One bag of tools.** `agent_started.data["avp.tools"]` and `descriptor.tools[]` carry every tool the agent can dispatch — local AND MCP-surfaced — in a single flat list.
- **`ToolDecl` gains an optional `avp.mcp_server_id`.** Local tools omit it; MCP-surfaced tools set it to the server's `id`, giving consumers a cross-reference into `mcp_servers[]` without nesting. The pre-invocation discriminator `avp.tool.dispatch_target` on `tool_invoked` stays.
- **`McpServerDecl` is identity + status.** Fields: `id`, optional `name`, optional `description`, optional `status` (`"connected" | "failed" | "needs-auth" | "pending" | "disabled"`). Same shape on `descriptor.mcp_servers[]` (status MAY be absent pre-flight) and `agent_started.data["avp.mcp_servers"][]` (status is the runtime state of each attempted dial). Slim wins over runtime metadata no consumer needs.
- **`mcp_servers[]` records attempted dials; `tools[]` records usable tools.** A server with `status: "failed" | "needs-auth" | "pending" | "disabled"` is on the wire so consumers can see what was attempted and how it ended. Its tools do NOT appear in `agent_started.data["avp.tools"]` — only tools from `status: "connected"` servers do. The authoritative "what can the model call this run" surface is `tools[]`, not `mcp_servers[]`.
- **No `resources` on the wire, anywhere.** `McpServerDecl` does NOT gain a `resources` field. `ResourceDecl` is deleted from `descriptor.py`. `mcp://` skill sources (which used to resolve through `resources/list` data on `mcp_server_connected`) are out-of-scope for v0.1; skills resolve internally if at all. If resources need to come back, it's a separate proposal with its own justification.
- **Agents preflight `tools/list` before emitting `agent_described`.** Cost of having a useful descriptor on the wire; one-time dial at startup.
- **Relax: descriptor on the wire SHOULD be consistent with `<agent> describe`, not MUST equal byte-for-byte.** Pre-flight `describe` MAY omit MCP-surfaced tools (no servers dialed yet); on-the-wire `agent_described` populates them. Lower bar for adoption.
- **`error_occurred(code: mcp_connect_failed)` fires only when a Commission-declared MCP server fails to dial.** The supervisor demanded that server; the loud event is the contract breach signal. The server itself still appears in `agent_started.data["avp.mcp_servers"]` with `status: "failed"`. Descriptor-internal (agent-bundled) failures: no `error_occurred` (the agent's own concern), but the server still appears with its terminal status so consumers see what was attempted.
- **Disconnects: no event.** Run-end is the disconnect.

## Checklists

### Spec

- [x] `spec/v0.1/trajectory.md`
  - [x] §1 table: drop `mcp_server_connected` / `mcp_server_disconnected` from "What the agent did"
  - [x] §2.1: prelude becomes 3 events (`run_requested` → `agent_described` → `agent_started`); rewrite agent_started bullet — `avp.tools[]` is the single merged bag of usable tools (local + MCP-surfaced from `status: "connected"` servers; entries carry optional `avp.mcp_server_id`); `avp.mcp_servers[]` records every attempted dial with `status` (connected/failed/needs-auth/pending/disabled)
  - [x] §3.2: drop the `for each mcp_server: emit mcp_server_connected` line; dial + `tools/list` happen silently between `agent_described` and `agent_started`
  - [x] §4 + §4.1: tool catalog is one bag on `agent_started.data["avp.tools"]`, populated only with tools from connected servers + local; MCP-surfaced entries carry `avp.mcp_server_id`; rewrite §4.1 step 2 to drop wire-emission step
  - [x] §7 event table: delete the two rows
  - [x] §8 conformance: delete M1 / M2; update #2 to the 3-event prelude + single-bag-of-usable-tools rule + mcp_servers-with-status rule; add MUST for `error_occurred(code: mcp_connect_failed)` when a **Commission-declared** server fails (descriptor-internal failures are silent); the failed server still appears in `mcp_servers[]` with `status: "failed"` in both cases
- [x] `spec/v0.1/agent-descriptor.md`
  - [x] Lines 125, 141, 197, 216: rewrite — `descriptor.tools[]` carries MCP-surfaced tools too (with `avp.mcp_server_id`); `descriptor.mcp_servers[]` stays identity-only
  - [x] Relax MUST to SHOULD for `agent_described.data["avp.descriptor"]` ↔ `<agent> describe` consistency; pre-flight describe MAY omit MCP-surfaced tool entries
- [x] Regenerate schemas + bindings: `make schemas && make bindings`. `make schemas` rewrites `spec/v0.1/{trajectory,agent-descriptor}.schema.json` from the Pydantic source; `make bindings` rewrites `rust/avp/src/*.rs` and `typescript/avp/src/*.ts` from those schemas. Drift detection (`make bindings-check`, run as part of `make check`) catches stale bindings.

### Pydantic source of truth (`python/avp/src/avp/`)

- [x] `descriptor.py`:
  - [x] `ToolDecl`: add optional `mcp_server_id: str | None = Field(default=None, alias="avp.mcp_server_id")`
  - [x] `McpServerDecl`: keep `id`, `name`, `description`; add `status: Literal["connected", "failed", "needs-auth", "pending", "disabled"] | None = None`; rewrite docstrings; drop dead refs to `mcp_server_connected`
  - [x] Drop `ResourceDecl` (no longer carried on the wire)
- [x] `trajectory.py`:
  - [x] Drop `T_MCP_SERVER_CONNECTED`, `T_MCP_SERVER_DISCONNECTED`
  - [x] Drop `McpServerConnectedData`, `McpServerDisconnectedData`, `McpServerConnectedEvent`, `McpServerDisconnectedEvent`
  - [x] Remove from `Event` discriminated union
  - [x] Add `ErrorCode.mcp_connect_failed`
  - [x] `AgentStartedData.mcp_servers` keeps the identity-only `McpServerDecl`; `AgentStartedData.tools` carries entries that may now include `avp.mcp_server_id`

### Integrator code

- [ ] `python/agents/avp-claude-agent-sdk/src/avp_claude_agent_sdk/_translator.py`: drop connect/disconnect emit paths; populate `agent_started.data["avp.tools"]` with MCP-surfaced entries (each carrying `avp.mcp_server_id`) sourced from `ClaudeSDKClient.get_mcp_status()` (or equivalent) at startup
- [ ] `python/agents/avp-claude-agent-sdk/tests/test_emit.py`: update assertions
- [ ] `python/agents/avp-claude-agent-sdk/{AVP_PLAN.md,TRAJECTORY_CHECKLIST.md}`: sweep refs

### Prose docs

- [ ] `FOUNDATIONS.md` lines 182, 417, 420
- [ ] `SKILL.md`, `conformance/v0.1/README.md`: sweep refs

### Verification

- [ ] `make check` (format + lint + tests + bindings drift) green. **Conformance cases are out of date and scoped out of this change** — they will be fixed in a separate pass, so `make check`'s conformance step may fail until then.
- [ ] `make smoke` (real-LLM matrix) green — wire change affects translator MCP-tools surfacing path

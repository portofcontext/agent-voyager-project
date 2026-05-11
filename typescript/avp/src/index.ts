/**
 * AVP — Agent Voyager Project v0.1 wire types.
 *
 * Types in this package are generated from the canonical JSON Schemas under
 * `spec/v0.1/` of the AVP repo. The Pydantic models in `python/avp/` are the
 * source of truth; the JSON Schemas are derived from them; these TypeScript
 * types are derived from the schemas. Single chain, no hand-maintained drift.
 *
 * ## Layout
 *
 * One module per AVP v0.1 sub-spec:
 *
 * - `commission` — `Commission`, the supervisor's setup message. Lists
 *   supervisor-managed assets (mcp_servers, skills, subagents) as opaque
 *   refs the agent dereferences via the AVP Resolver API at startup.
 *   Sent once at run start.
 * - `trajectory` — agent-emitted events. The `AVPV01TrajectoryEvent`
 *   discriminated union is what your code matches on when consuming a
 *   trajectory.
 * - `agentDescriptor` — the agent's self-description shape (carried on
 *   `agent_described.data["avp.descriptor"]` and printed by
 *   `<agent> describe`).
 *
 * v0.1 has no supervisor → agent push channel. The supervisor pipes
 * `Commission` in once and reads the NDJSON trajectory out. The agent
 * initiates an `avp.resolve` JSON-RPC call to a supervisor-stood-up
 * resolver service to dereference each managed ref; agent-driven, no push.
 *
 * ## Regenerating
 *
 * Bindings are committed (not generated at build time). To regenerate after
 * a spec bump:
 *
 * ```bash
 * scripts/generate-bindings.sh
 * ```
 */

// Top-level message classes — what most consumers import.
export type { AVPV01Commission as Commission } from "./commission.js";
export type { AVPV01TrajectoryEvent as Event } from "./trajectory.js";
export type { AVPV01AgentDescriptor as AgentDescriptor } from "./agent-descriptor.js";

// Module re-exports for callers that need the helper types
// (data shapes, individual event variants, etc.).
export * as commission from "./commission.js";
export * as trajectory from "./trajectory.js";
export * as agentDescriptor from "./agent-descriptor.js";

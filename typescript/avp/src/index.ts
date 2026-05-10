/**
 * AVP — Agent Voyage Protocol v0.1 wire types.
 *
 * Types in this package are generated from the canonical JSON Schemas under
 * `spec/v0.1/` of the AVP repo. The Pydantic models in `python/avp/` are the
 * source of truth; the JSON Schemas are derived from them; these TypeScript
 * types are derived from the schemas. Single chain, no hand-maintained drift.
 *
 * ## Layout
 *
 * Two modules, one per top-level message class:
 *
 * - `commission` — `Commission`, the supervisor's setup message. Lists
 *   supervisor-managed assets (mcp_servers, skills, subagents) as opaque
 *   refs the agent dereferences via the AVP resolver protocol at startup.
 *   Sent once at run start.
 * - `event` — agent-emitted events. The `AVPV01Event` discriminated union
 *   is what your code matches on when consuming a trajectory.
 *
 * v0.1 has no supervisor → agent push channel. The supervisor pipes
 * `Commission` in once and reads the NDJSON event stream out. The agent
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
export type { AVPV01Event as Event } from "./event.js";

// Module re-exports for callers that need the helper types
// (data shapes, individual event variants, etc.).
export * as commission from "./commission.js";
export * as event from "./event.js";

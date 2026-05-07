/**
 * AEP — Agent Execution Protocol v0.1 wire types.
 *
 * Types in this package are generated from the canonical JSON Schemas under
 * `spec/v0.1/` of the AEP repo. The Pydantic models in `python/aep/` are the
 * source of truth; the JSON Schemas are derived from them; these TypeScript
 * types are derived from the schemas. Single chain, no hand-maintained drift.
 *
 * ## Layout
 *
 * Three modules, one per top-level message class:
 *
 * - `config` — `Config`, the supervisor's setup message (boundary, tools,
 *   verifiers, mcp_servers, skills, prompts). Sent once at run start.
 * - `event` — runner-emitted events. The `AEPV01Event` discriminated union
 *   is what your code matches on when consuming a trajectory.
 * - `supervisor-message` — supervisor → runner replies (tool_exec_resolved
 *   and approval_resolved RPC reply shapes).
 *
 * Helper types like `JsonRpcRequestPayload` exist in multiple modules because
 * `json-schema-to-typescript` generates per-file. They're equivalent on the
 * wire; pick the module-scoped one that matches what you're deserializing.
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
export type { AEPV01Config as Config } from "./config.js";
export type { AEPV01Event as Event } from "./event.js";
export type { AEPV01SupervisorMessage as SupervisorMessage } from "./supervisor-message.js";

// Module re-exports for callers that need the helper types
// (data shapes, individual event variants, etc.).
export * as config from "./config.js";
export * as event from "./event.js";
export * as supervisor from "./supervisor-message.js";

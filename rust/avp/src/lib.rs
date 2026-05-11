//! AVP — Agent Voyager Project v0.1 wire types.
//!
//! Types in this crate are generated from the canonical JSON Schemas under
//! `spec/v0.1/` of the AVP repo. The Pydantic models in `python/avp/` are the
//! source of truth; the JSON Schemas are derived from them; these Rust types
//! are derived from the schemas. Single chain, no hand-maintained drift.
//!
//! ## Layout
//!
//! One module per AVP v0.1 spec:
//!
//! - [`commission`] — `Commission`, the supervisor's setup message. Lists
//!   supervisor-managed assets (mcp_servers, skills, subagents) as opaque
//!   refs the agent dereferences via the AVP Resolver API at startup.
//!   Sent once at run start.
//! - [`trajectory`] — agent-emitted events. The discriminated
//!   [`trajectory::AvpV01TrajectoryEvent`] union is what your code matches
//!   on when consuming a trajectory.
//! - [`agent_descriptor`] — the agent's self-description shape (carried on
//!   `agent_described.data["avp.descriptor"]` and printed by
//!   `<agent> describe`).
//!
//! v0.1 has no supervisor → agent push channel. The supervisor pipes
//! `Commission` in once and reads the NDJSON trajectory out. The agent
//! initiates an `avp.resolve` JSON-RPC call to a supervisor-stood-up
//! resolver service to dereference each managed ref; agent-driven, no push.
//!
//! ## Regenerating
//!
//! Bindings are committed (not generated at build time) so consumers don't
//! need a build dependency on `cargo-typify`. To regenerate after a spec bump:
//!
//! ```bash
//! scripts/generate-bindings.sh
//! ```
//!
//! `make check` includes a regen-and-diff step that fails CI if generated
//! code drifts from the schemas.

#![allow(clippy::all)]
#![allow(missing_docs)]

pub mod agent_descriptor;
pub mod commission;
pub mod trajectory;

/// Re-export the Agent Descriptor under its canonical name.
pub use agent_descriptor::AvpV01AgentDescriptor as AgentDescriptor;
/// Re-export the top-level Commission struct (typify generates it as
/// `AvpV01Commission`; we re-export under the canonical name).
pub use commission::AvpV01Commission as Commission;
/// Re-export the discriminated trajectory-event union under a friendlier name.
pub use trajectory::AvpV01TrajectoryEvent as Event;

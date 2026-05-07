//! AEP — Agent Execution Protocol v0.1 wire types.
//!
//! Types in this crate are generated from the canonical JSON Schemas under
//! `spec/v0.1/` of the AEP repo. The Pydantic models in `python/aep/` are the
//! source of truth; the JSON Schemas are derived from them; these Rust types
//! are derived from the schemas. Single chain, no hand-maintained drift.
//!
//! ## Layout
//!
//! Three modules, one per top-level message class:
//!
//! - [`config`] — `Config`, the supervisor's setup message (boundary, tools,
//!   verifiers, mcp_servers, skills, prompts). Sent once at run start.
//! - [`event`] — runner-emitted events. The discriminated [`event::AepV01Event`]
//!   union is what your code matches on when consuming a trajectory.
//! - [`supervisor_message`] — supervisor → runner replies. v0.1 carries
//!   `tool_exec_resolved` and `approval_resolved` (the two RPC reply shapes).
//!
//! Helper types like `JsonRpcRequestPayload` exist in multiple modules because
//! `cargo-typify` can't follow `$ref` across schema files. They're equivalent
//! by serde wire shape; pick the module-scoped one that matches what you're
//! deserializing.
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

pub mod config;
pub mod event;
pub mod supervisor_message;

/// Re-export the top-level Config struct (typify generates it as
/// `AepV01Config`; we re-export under the canonical name).
pub use config::AepV01Config as Config;
/// Re-export the discriminated event union under a friendlier name.
pub use event::AepV01Event as Event;
/// Re-export the supervisor-message union.
pub use supervisor_message::AepV01SupervisorMessage as SupervisorMessage;

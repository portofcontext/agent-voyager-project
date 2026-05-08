//! AVP — Agent Voyage Protocol v0.1 wire types.
//!
//! Types in this crate are generated from the canonical JSON Schemas under
//! `spec/v0.1/` of the AVP repo. The Pydantic models in `python/avp/` are the
//! source of truth; the JSON Schemas are derived from them; these Rust types
//! are derived from the schemas. Single chain, no hand-maintained drift.
//!
//! ## Layout
//!
//! Two modules, one per top-level message class:
//!
//! - [`commission`] — `Commission`, the supervisor's setup message (mcp_servers,
//!   allowed_tools, skills, subagents, prompts). Sent once at run start.
//! - [`event`] — agent-emitted events. The discriminated [`event::AvpV01Event`]
//!   union is what your code matches on when consuming a trajectory.
//!
//! v0.1 has no supervisor → agent channel. The supervisor pipes `Commission` in
//! once and reads the NDJSON event stream out; nothing else flows back.
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

pub mod commission;
pub mod event;

/// Re-export the top-level Commission struct (typify generates it as
/// `AvpV01Commission`; we re-export under the canonical name).
pub use commission::AvpV01Commission as Commission;
/// Re-export the discriminated event union under a friendlier name.
pub use event::AvpV01Event as Event;

//! AVP connector for Block's Goose coding agent.
//!
//! Observes Goose's internal `AgentEvent` stream and emits an AVP trajectory.
//! See `DESIGN.md` for the architecture. This crate is built to run and demo
//! in-repo; the connector is intended to be upstreamed into the Goose tree as
//! an opt-in observer once stable.

pub mod commission;
pub mod emit;
pub mod events;
pub mod provider_tap;
pub mod runner;
pub mod runstate;
pub mod translate;

#[cfg(test)]
mod testkit;

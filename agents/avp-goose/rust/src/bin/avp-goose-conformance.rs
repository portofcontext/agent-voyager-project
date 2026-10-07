//! Agent entrypoint for avp-goose (`ping` / `describe` / `run`).
//!
//! The command line is the binding's stock `avp::agent_cli`; this binary
//! supplies the two Goose pieces, blocking on a Tokio runtime:
//!
//! - `describe` boots a default agent to list its built-in tools, degrading to
//!   an identity-only descriptor if the probe can't run.
//! - `run` drives a live Goose run from the Commission.
//!
//! Goose's tool / MCP / subagent catalog is baked into the framework and can't
//! be swapped for a `--built-in` fixture's, so cases that inject those
//! built-ins are a known Goose conformance gap.

use std::process::ExitCode;

fn main() -> ExitCode {
    let runtime = tokio::runtime::Runtime::new().expect("tokio runtime");
    avp::agent_cli::main(
        || Ok(runtime.block_on(avp_goose::runner::describe())?),
        |commission, sink| Ok(runtime.block_on(avp_goose::runner::run(&commission, sink))?),
    )
}

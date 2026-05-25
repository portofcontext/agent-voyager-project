//! Conformance entrypoint for avp-goose.
//!
//! Implements the agent CLI contract consumed by `avp-conformance`:
//!
//! - `ping --out <path>` — write a single `{"type": "pong"}` line and exit.
//!
//! Gated behind the `conformance` Cargo feature so the clap dependency
//! and this binary are only built when the harness needs them.

use std::fs;
use std::path::PathBuf;

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "avp-goose-conformance", about = "Conformance entrypoint for avp-goose.")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Write {"type": "pong"} to --out and exit.
    Ping {
        #[arg(long)]
        out: PathBuf,
    },
}

fn main() -> anyhow::Result<()> {
    match Cli::parse().cmd {
        Cmd::Ping { out } => {
            fs::write(out, "{\"type\":\"pong\"}\n")?;
            Ok(())
        }
    }
}

//! Conformance entrypoint for avp-goose.
//!
//! Implements the agent CLI contract consumed by `avp-conformance`:
//!
//! - `ping --out <path>` — write a single `{"type": "pong"}` line and exit.
//! - `run --commission <json|path> [--built-in <json|path>] --out <path>` —
//!   drive a live Goose run from the Commission and stream the AVP trajectory
//!   as NDJSON to `--out`.
//!
//! Gated behind the `conformance` Cargo feature so the clap dependency
//! and this binary are only built when the harness needs them.
//!
//! `--built-in` (the case's `AgentBuiltins` fixture) is honored only where
//! Goose can actually simulate it: `system_prompt` and `prompt` seed the run
//! as defaults, with the Commission overriding when it speaks to the same
//! field. Goose's tool / MCP / subagent catalog is baked into the framework
//! and cannot be swapped for arbitrary fixtures, so cases that inject those
//! built-ins are a known goose conformance gap (see `AgentBuiltins` docs in
//! `python/avp/src/avp/conformance/case.py`).

use std::path::PathBuf;

use avp::sink::FileSink;
use avp::Commission;
use clap::{Parser, Subcommand};
use serde_json::Value;

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
    /// Run a Commission live against Goose, streaming the trajectory to --out.
    Run {
        /// Inline Commission JSON or a path to a JSON file.
        #[arg(long)]
        commission: String,
        /// Inline AgentBuiltins JSON or a path to a JSON file (optional fixture).
        #[arg(long = "built-in")]
        built_in: Option<String>,
        /// Path the NDJSON trajectory is written to, one event per line.
        #[arg(long)]
        out: PathBuf,
    },
}

/// Parse a CLI arg that is either inline JSON or a path to a JSON file.
/// Mirrors `avp.conformance._utils.read_json_arg`: a leading `{`/`[` (after
/// whitespace) means inline JSON; anything else is read as a file path.
fn read_json_arg(value: &str) -> anyhow::Result<Value> {
    let trimmed = value.trim_start();
    if trimmed.starts_with('{') || trimmed.starts_with('[') {
        Ok(serde_json::from_str(value)?)
    } else {
        Ok(serde_json::from_str(&std::fs::read_to_string(value)?)?)
    }
}

/// Seed Commission fields from the built-in fixture where Goose can honor it.
/// The fixture is the agent's pretend default; the Commission overrides it, so
/// a field is only filled from the fixture when the Commission leaves it unset.
fn apply_built_in(commission: &mut Commission, built_in: &Value) {
    if commission.system_prompt.is_none() {
        if let Some(s) = built_in.get("system_prompt").and_then(Value::as_str) {
            commission.system_prompt = Some(s.to_string());
        }
    }
    if commission.prompt.is_none() {
        if let Some(s) = built_in.get("prompt").and_then(Value::as_str) {
            commission.prompt = Some(s.to_string());
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    match Cli::parse().cmd {
        Cmd::Ping { out } => {
            std::fs::write(out, "{\"type\":\"pong\"}\n")?;
            Ok(())
        }
        Cmd::Run {
            commission,
            built_in,
            out,
        } => {
            let mut commission: Commission = serde_json::from_value(read_json_arg(&commission)?)?;
            if let Some(built_in) = built_in {
                apply_built_in(&mut commission, &read_json_arg(&built_in)?);
            }
            let sink = FileSink::create(&out)?;
            avp_goose::runner::run(&commission, sink).await
        }
    }
}

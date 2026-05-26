//! Run an AVP Commission live against Goose, streaming the trajectory as NDJSON.
//!
//! Reads a Commission JSON from a file argument or stdin, drives a live Goose
//! `Agent`, and emits the AVP trajectory to stdout one event per line.
//!
//!   avp-goose-run commission.json        # from file
//!   echo '{...}' | avp-goose-run          # from stdin
//!
//! Requires the provider's credentials in the environment (e.g.
//! `ANTHROPIC_API_KEY`); this build does not link the system keyring.

use std::io::Read;

use avp::sink::StdioSink;
use avp::Commission;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let raw = match std::env::args().nth(1) {
        Some(path) => std::fs::read_to_string(path)?,
        None => {
            let mut buf = String::new();
            std::io::stdin().read_to_string(&mut buf)?;
            buf
        }
    };
    let commission: Commission = serde_json::from_str(&raw)?;
    avp_goose::runner::run(&commission, StdioSink).await
}

//! The whole thing: hand Goose a Commission, stream a conformant AVP trajectory.
//!
//!   ANTHROPIC_API_KEY=sk-... \
//!     cargo run -p avp-goose --example tiny
//!
//! Every step of the run (model turns, tool calls, tokens, cost, stop reason)
//! leaves as one AVP event. `StdioSink` writes them as NDJSON; implement the
//! one-method `Sink` trait to handle them however you like instead.

use avp::{Commission, StdioSink};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // A Commission is the entire run config: model, prompt, tools, MCP servers,
    // skills. This one lets the agent use the shell.
    let commission: Commission = serde_json::from_value(serde_json::json!({
        "schema_version": "0.1",
        "run_id": "tiny-demo",
        "model": "anthropic/claude-sonnet-4-6",
        "prompt": "Use the shell to print today's date, then tell me what it is.",
        "enabled_builtin_tools": ["developer"],
    }))?;

    // Run it on Goose. That's it.
    avp_goose::runner::run(&commission, StdioSink).await
}

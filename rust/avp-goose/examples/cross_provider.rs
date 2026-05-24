//! Same code, any provider. A Commission carries the `model`; Goose resolves
//! the provider from `GOOSE_PROVIDER`, so this identical program runs on
//! Anthropic or OpenRouter (or anything Goose speaks) by swapping two env vars,
//! and emits the same AVP trajectory shape either way:
//!
//!   GOOSE_PROVIDER=anthropic  AVP_MODEL=claude-sonnet-4-6  ANTHROPIC_API_KEY=sk-... \
//!     cargo run -p avp-goose --example cross_provider
//!
//!   GOOSE_PROVIDER=openrouter AVP_MODEL=openai/gpt-4o      OPENROUTER_API_KEY=sk-or-... \
//!     cargo run -p avp-goose --example cross_provider

use avp::{Commission, StdioSink};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let provider = std::env::var("GOOSE_PROVIDER").unwrap_or_else(|_| "anthropic".into());
    let model = std::env::var("AVP_MODEL").unwrap_or_else(|_| "claude-sonnet-4-6".into());
    eprintln!("# running on {provider} / {model}");

    // The only provider-specific thing here is the model string. Everything
    // else, the trajectory, the cost accounting, the event shape, is identical.
    let commission: Commission = serde_json::from_value(serde_json::json!({
        "schema_version": "0.1",
        "run_id": "cross-provider-demo",
        "model": model,
        "prompt": "In one short sentence, what does a coding agent do?",
    }))?;

    avp_goose::runner::run(&commission, StdioSink).await
}

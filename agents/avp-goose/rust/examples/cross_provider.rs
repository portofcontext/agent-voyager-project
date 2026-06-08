//! Same code, any provider. A Commission carries the canonical `origin/model`
//! slug plus an optional `provider` block naming the storefront; Goose routes
//! to it. One env var picks the storefront, so this identical program runs on
//! Anthropic or OpenRouter and emits the same AVP trajectory shape either way.
//! Credentials are vault handles, resolved out of band (here, the supervisor's
//! `AVP_VAULT_<HANDLE>` env):
//!
//!   # Anthropic (the default)
//!   ANTHROPIC_API_KEY=sk-... \
//!     cargo run -p avp-goose --example cross_provider
//!
//!   # OpenRouter
//!   AVP_PROVIDER=openrouter AVP_VAULT_OPENROUTER=sk-or-... \
//!     cargo run -p avp-goose --example cross_provider

use avp::{Commission, StdioSink};
use serde_json::json;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // The only provider-specific things are the model slug and the provider
    // block. Everything else, the trajectory, the cost accounting, the event
    // shape, is identical.
    let (model, provider) = match std::env::var("AVP_PROVIDER").as_deref() {
        Ok("openrouter") => (
            "openai/gpt-4o",
            json!({ "id": "openrouter", "credential": { "vault": "openrouter" } }),
        ),
        _ => ("anthropic/claude-sonnet-4-6", json!({ "id": "anthropic" })),
    };
    eprintln!("# running model {model}");

    let commission: Commission = serde_json::from_value(json!({
        "schema_version": "0.1",
        "run_id": "cross-provider-demo",
        "model": model,
        "provider": provider,
        "prompt": "In one short sentence, what does a coding agent do?",
    }))?;

    avp_goose::runner::run(&commission, StdioSink).await
}

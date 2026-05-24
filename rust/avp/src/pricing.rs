//! Shared model pricing for AVP agents.
//!
//! The agent stamps `avp.cost.source` on each `assistant_message` so consumers
//! can tell a locally-computed cost from a provider-reported one (or unknown).
//! The price table is data: the default ships in `src/data/prices.json`,
//! embedded at build time. Callers may build or override their own `PriceTable`.

use std::collections::HashMap;

use serde::Deserialize;

/// Provenance of a cost number on the wire. Re-export of the generated wire
/// enum so a computed cost can be stamped directly onto `assistant_message`.
pub use crate::trajectory::AssistantMessageDataAvpCostSource as CostSource;

/// Per-1M-token pricing in USD.
#[derive(Debug, Clone, Deserialize)]
pub struct ModelPrice {
    pub input: f64,
    pub output: f64,
    #[serde(default)]
    pub cache_read: f64,
    #[serde(default)]
    pub cache_write: f64,
}

/// A model-name to price mapping. Callers may build or override their own.
pub type PriceTable = HashMap<String, ModelPrice>;

#[derive(Deserialize)]
struct PriceFile {
    models: HashMap<String, ModelPrice>,
}

const PRICES_JSON: &str = include_str!("data/prices.json");

/// Load the bundled default price table. Returns a fresh, owned table the
/// caller can mutate.
pub fn load_default_prices() -> PriceTable {
    let file: PriceFile =
        serde_json::from_str(PRICES_JSON).expect("bundled prices.json is valid JSON");
    file.models
}

/// Resolve a price by the model the agent put on the wire.
///
/// The bundled table is mirrored from models.dev and keyed by its
/// `<provider>/<model>` id. A wire `model` is either already a slug containing a
/// provider (`openai/gpt-4o`, used as-is) or a bare provider-native string
/// (`claude-sonnet-4-6`) that is qualified with `provider` to form the key
/// (`anthropic/claude-sonnet-4-6`). The exact string is tried first so a custom
/// table keyed by bare names still works.
pub fn resolve_price<'a>(
    prices: &'a PriceTable,
    provider: Option<&str>,
    model: &str,
) -> Option<&'a ModelPrice> {
    if let Some(p) = prices.get(model) {
        return Some(p);
    }
    match provider {
        Some(prov) if !model.contains('/') => prices.get(&format!("{prov}/{model}")),
        _ => None,
    }
}

/// Compute billable USD cost from a turn's token counts, returning the cost
/// and its provenance.
///
/// `provider` is the model's provider (e.g. `"anthropic"`), used to resolve a
/// bare wire model against the `<provider>/<model>`-keyed table; pass `None` if
/// the wire model is already provider-qualified or unknown.
///
/// `input_tokens` follows the AVP convention: cache reads are INCLUDED. Cache
/// reads and writes are billed at their own rates; the fresh remainder gets
/// the regular input rate. An unknown model returns `(0.0, Unknown)` so the
/// caller can flag a silent under-count rather than ship a wrong number.
pub fn compute_cost(
    provider: Option<&str>,
    model: &str,
    input_tokens: u64,
    output_tokens: u64,
    cache_read: u64,
    cache_write: u64,
    prices: &PriceTable,
) -> (f64, CostSource) {
    let Some(p) = resolve_price(prices, provider, model) else {
        return (0.0, CostSource::Unknown);
    };
    let fresh = input_tokens
        .saturating_sub(cache_read)
        .saturating_sub(cache_write);
    let cost = fresh as f64 * p.input / 1_000_000.0
        + cache_read as f64 * p.cache_read / 1_000_000.0
        + cache_write as f64 * p.cache_write / 1_000_000.0
        + output_tokens as f64 * p.output / 1_000_000.0;
    (cost, CostSource::Computed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_table_loads() {
        let t = load_default_prices();
        // Mirrored from models.dev, keyed by `<provider>/<model>`.
        let p = t.get("anthropic/claude-opus-4-7").expect("opus 4.7 in default table");
        assert_eq!(p.input, 5.0);
        assert_eq!(p.output, 25.0);
    }

    #[test]
    fn computes_with_cache_split() {
        // fresh = 1000 - 200 - 100 = 700.
        // 700*5 + 200*0.5 + 100*6.25 + 500*25 = 3500 + 100 + 625 + 12500 = 16725 (per 1e6).
        let prices = load_default_prices();
        // Bare wire model is resolved via the provider to `anthropic/claude-opus-4-7`.
        let (cost, src) = compute_cost(Some("anthropic"), "claude-opus-4-7", 1000, 500, 200, 100, &prices);
        assert!((cost - 0.016725).abs() < 1e-9, "got {cost}");
        assert_eq!(src, CostSource::Computed);
    }

    #[test]
    fn slug_model_resolves_without_provider() {
        // A provider-qualified wire slug is used as the key as-is.
        let prices = load_default_prices();
        let (cost, src) = compute_cost(None, "openai/gpt-4o", 1_000_000, 0, 0, 0, &prices);
        assert_eq!(src, CostSource::Computed);
        assert!((cost - 2.5).abs() < 1e-9, "got {cost}");
    }

    #[test]
    fn unknown_model_is_zero_unknown() {
        let prices = load_default_prices();
        let (cost, src) = compute_cost(Some("nope"), "unknown", 1000, 500, 0, 0, &prices);
        assert_eq!(cost, 0.0);
        assert_eq!(src, CostSource::Unknown);
    }
}

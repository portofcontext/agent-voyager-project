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

/// Compute billable USD cost from a turn's token counts, returning the cost
/// and its provenance.
///
/// `input_tokens` follows the AVP convention: cache reads are INCLUDED. Cache
/// reads and writes are billed at their own rates; the fresh remainder gets
/// the regular input rate. An unknown model returns `(0.0, Unknown)` so the
/// caller can flag a silent under-count rather than ship a wrong number.
pub fn compute_cost(
    model: &str,
    input_tokens: u64,
    output_tokens: u64,
    cache_read: u64,
    cache_write: u64,
    prices: &PriceTable,
) -> (f64, CostSource) {
    let Some(p) = prices.get(model) else {
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
        let p = t.get("claude-opus-4-7").expect("opus 4.7 in default table");
        assert_eq!(p.input, 5.0);
        assert_eq!(p.output, 25.0);
    }

    #[test]
    fn computes_with_cache_split() {
        // fresh = 1000 - 200 - 100 = 700.
        // 700*5 + 200*0.5 + 100*6.25 + 500*25 = 3500 + 100 + 625 + 12500 = 16725 (per 1e6).
        let prices = load_default_prices();
        let (cost, src) = compute_cost("claude-opus-4-7", 1000, 500, 200, 100, &prices);
        assert!((cost - 0.016725).abs() < 1e-9, "got {cost}");
        assert_eq!(src, CostSource::Computed);
    }

    #[test]
    fn unknown_model_is_zero_unknown() {
        let prices = load_default_prices();
        let (cost, src) = compute_cost("nope/unknown", 1000, 500, 0, 0, &prices);
        assert_eq!(cost, 0.0);
        assert_eq!(src, CostSource::Unknown);
    }
}

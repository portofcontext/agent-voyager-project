use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    time::Duration,
};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{Result, commission::ModelRef, trajectory::CostSource};

use super::models_dev::{self, Snapshot};
const FILE: &str = "avp_prices.json";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields, try_from = "RawPrice")]
pub struct ModelPrice {
    pub input: f64,
    pub output: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_read: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_write: Option<f64>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawPrice {
    input: f64,
    output: f64,
    cache_read: Option<f64>,
    cache_write: Option<f64>,
}

impl TryFrom<RawPrice> for ModelPrice {
    type Error = &'static str;
    fn try_from(p: RawPrice) -> std::result::Result<Self, Self::Error> {
        if [Some(p.input), Some(p.output), p.cache_read, p.cache_write]
            .into_iter()
            .flatten()
            .any(|p| p < 0.0)
        {
            return Err("prices must be non-negative");
        }
        Ok(Self {
            input: p.input,
            output: p.output,
            cache_read: p.cache_read,
            cache_write: p.cache_write,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Prices {
    #[serde(default = "models_dev::source")]
    pub source: String,
    pub fetched: DateTime<Utc>,
    pub models: BTreeMap<String, ModelPrice>,
}

impl Snapshot for Prices {
    fn fetched(&self) -> DateTime<Utc> {
        self.fetched
    }
}

pub fn bundled_prices() -> Prices {
    serde_json::from_str(include_str!("data/avp_prices.json")).expect("bundled prices are valid")
}

pub fn default_cache_path() -> PathBuf {
    models_dev::cache_path(FILE)
}

pub fn fetch_prices(catalog: Option<&Value>) -> Result<Prices> {
    let catalog = models_dev::catalog(catalog)?;
    let mut models = BTreeMap::new();
    for (provider_id, provider) in catalog.as_object().ok_or("catalog must be an object")? {
        if let Some(entries) = provider.get("models").and_then(Value::as_object) {
            for (model_id, model) in entries {
                let Some(cost) = model.get("cost") else {
                    continue;
                };
                if cost.get("input").is_none_or(Value::is_null)
                    || cost.get("output").is_none_or(Value::is_null)
                {
                    continue;
                }
                models.insert(format!("{provider_id}/{model_id}"), serde_json::from_value(serde_json::json!({
                    "input": cost["input"], "output": cost["output"],
                    "cache_read": cost.get("cache_read"), "cache_write": cost.get("cache_write"),
                }))?);
            }
        }
    }
    Ok(Prices {
        source: models_dev::source(),
        fetched: Utc::now(),
        models,
    })
}

pub fn save_prices(prices: &Prices, path: Option<&Path>) -> Result<PathBuf> {
    models_dev::save(
        prices,
        &path
            .map(Path::to_path_buf)
            .unwrap_or_else(default_cache_path),
    )
}

pub fn load_prices(path: Option<&Path>, max_age: Option<Duration>) -> Result<Prices> {
    load(path, &default_cache_path(), max_age, || fetch_prices(None))
}

fn load(
    path: Option<&Path>,
    default_path: &Path,
    max_age: Option<Duration>,
    fetch: impl FnOnce() -> Result<Prices>,
) -> Result<Prices> {
    models_dev::load(path, default_path, max_age, bundled_prices, fetch)
}

pub fn find_price<'a>(
    prices: &'a Prices,
    model: &ModelRef,
    response_model: Option<&str>,
) -> Option<&'a ModelPrice> {
    [response_model, Some(model.id.as_str())]
        .into_iter()
        .flatten()
        .filter(|id| !id.is_empty())
        .find_map(|id| {
            prices
                .models
                .get(&format!("{}/{id}", model.provider.as_str()))
        })
}

#[derive(Debug, Default)]
pub struct Tokens {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_input_tokens: u64,
    pub cache_creation_input_tokens: u64,
}

pub fn compute_cost(
    prices: &Prices,
    model: &ModelRef,
    tokens: &Tokens,
    response_model: Option<&str>,
    reported_cost_usd: Option<f64>,
) -> Result<(f64, CostSource)> {
    if let Some(cost) = reported_cost_usd {
        return Ok((cost, CostSource::Reported));
    }
    let Some(price) = find_price(prices, model, response_model) else {
        return Ok((0.0, CostSource::Unknown));
    };
    let uncached = tokens
        .input_tokens
        .checked_sub(tokens.cache_read_input_tokens)
        .and_then(|n| n.checked_sub(tokens.cache_creation_input_tokens))
        .ok_or("cache read and creation tokens exceed input_tokens")?;
    let cost = (uncached as f64 * price.input
        + tokens.cache_read_input_tokens as f64 * price.cache_read.unwrap_or(price.input)
        + tokens.cache_creation_input_tokens as f64 * price.cache_write.unwrap_or(price.input)
        + tokens.output_tokens as f64 * price.output)
        / 1_000_000.0;
    Ok((cost, CostSource::Computed))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::{cell::Cell, fs};

    fn table() -> Prices {
        serde_json::from_value(json!({"fetched": Utc::now(), "models": {
            "p/model": {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75},
            "p/dated": {"input": 1, "output": 1}, "p/plain": {"input": 2, "output": 8}
        }}))
        .unwrap()
    }

    #[test]
    fn pricing_uses_provider_response_id_cache_rates_and_reported_cost() {
        let prices = table();
        let model: ModelRef =
            serde_json::from_value(json!({"provider": "p", "id": "model"})).unwrap();
        let tokens = Tokens {
            input_tokens: 3_000_000,
            cache_read_input_tokens: 1_000_000,
            cache_creation_input_tokens: 1_000_000,
            ..Default::default()
        };
        assert_eq!(
            compute_cost(&prices, &model, &tokens, None, None).unwrap(),
            (7.05, CostSource::Computed)
        );
        assert_eq!(
            compute_cost(&prices, &model, &tokens, Some("dated"), None)
                .unwrap()
                .0,
            3.0
        );
        assert_eq!(
            compute_cost(&prices, &model, &tokens, Some("missing"), None)
                .unwrap()
                .0,
            7.05
        );
        assert_eq!(
            compute_cost(&prices, &model, &tokens, None, Some(0.0)).unwrap(),
            (0.0, CostSource::Reported)
        );
        let other: ModelRef =
            serde_json::from_value(json!({"provider": "other", "id": "model"})).unwrap();
        assert_eq!(
            compute_cost(&prices, &other, &tokens, None, None).unwrap(),
            (0.0, CostSource::Unknown)
        );
        let plain: ModelRef =
            serde_json::from_value(json!({"provider": "p", "id": "plain"})).unwrap();
        assert_eq!(
            compute_cost(&prices, &plain, &tokens, None, None)
                .unwrap()
                .0,
            6.0
        );
        assert!(
            compute_cost(
                &prices,
                &model,
                &Tokens {
                    input_tokens: 1,
                    cache_read_input_tokens: 2,
                    ..Default::default()
                },
                None,
                None
            )
            .is_err()
        );
    }

    #[test]
    fn snapshots_round_trip_and_only_refresh_when_requested() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested/prices.json");
        let prices = table();
        let fetches = Cell::new(0);
        let fetch = || {
            fetches.set(fetches.get() + 1);
            Ok(prices.clone())
        };
        assert!(load(Some(&path), &path, None, fetch).is_err());
        assert_eq!(fetches.get(), 0);
        assert_eq!(
            load(Some(&path), &path, Some(Duration::from_secs(3600)), fetch).unwrap(),
            prices
        );
        assert_eq!(load(Some(&path), &path, None, fetch).unwrap(), prices);
        assert_eq!(fetches.get(), 1);
        let mut stale = prices.clone();
        stale.fetched -= chrono::Duration::days(2);
        save_prices(&stale, Some(&path)).unwrap();
        assert_eq!(
            load(
                Some(&path),
                &path,
                Some(Duration::from_secs(3 * 86400)),
                fetch
            )
            .unwrap(),
            stale
        );
        assert_eq!(
            load(Some(&path), &path, Some(Duration::from_secs(86400)), fetch).unwrap(),
            prices
        );
        assert_eq!(fetches.get(), 2);
        assert!(!path.with_file_name(".prices.json.partial").exists());
        fs::write(&path, "broken JSON").unwrap();
        assert!(load(Some(&path), &path, Some(Duration::ZERO), fetch).is_err());
        assert_eq!(fetches.get(), 2);
    }

    #[test]
    fn default_loading_prefers_the_newer_snapshot_without_fetching() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("prices.json");
        let shipped = bundled_prices();
        let no_fetch = || -> Result<Prices> { panic!("offline loading fetched prices") };
        assert_eq!(load(None, &path, None, no_fetch).unwrap(), shipped);
        let mut cached = table();
        cached.fetched = shipped.fetched - chrono::Duration::days(1);
        save_prices(&cached, Some(&path)).unwrap();
        assert_eq!(load(None, &path, None, no_fetch).unwrap(), shipped);
        cached.fetched = shipped.fetched + chrono::Duration::days(1);
        save_prices(&cached, Some(&path)).unwrap();
        assert_eq!(load(None, &path, None, no_fetch).unwrap(), cached);
    }

    #[test]
    fn catalog_conversion_and_snapshot_validation() {
        let prices = fetch_prices(Some(&json!({"p": {"models": {
            "free": {"cost": {"input": 0, "output": 0}},
            "partial": {"cost": {"input": 2}}, "none": {},
            "cached": {"cost": {"input": 2, "output": 8, "cache_read": 0.5, "extra": 1}}
        }}})))
        .unwrap();
        assert_eq!(
            prices.models.keys().collect::<Vec<_>>(),
            ["p/cached", "p/free"]
        );
        assert_eq!(prices.models["p/cached"].cache_read, Some(0.5));
        assert!(serde_json::from_value::<ModelPrice>(json!({"input": -1, "output": 1})).is_err());
        assert!(
            serde_json::from_value::<ModelPrice>(json!({"input": 1, "output": 1, "extra": 2}))
                .is_err()
        );
    }
}

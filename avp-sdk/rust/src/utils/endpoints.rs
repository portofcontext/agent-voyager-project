//! Provider URLs and API-key headers for egress, metering, and credential proxies.
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    time::Duration,
};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::models_dev::{self, Snapshot};
use crate::Result;

const FILE: &str = "avp_endpoints.json";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Auth {
    pub header: String,
    #[serde(default)]
    pub prefix: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Endpoint {
    /// Absent when the URL depends on an account or region.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base_url: Option<String>,
    /// Absent when a proxy cannot add a fixed API-key header.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auth: Option<Auth>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Endpoints {
    #[serde(default = "models_dev::source")]
    pub source: String,
    pub fetched: DateTime<Utc>,
    pub providers: BTreeMap<String, Endpoint>,
}

impl Snapshot for Endpoints {
    fn fetched(&self) -> DateTime<Utc> {
        self.fetched
    }
}

/// Shared URL fallbacks and fixed API-key headers. Bedrock means API keys, not SigV4.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EndpointDefaults {
    pub gap_fillers: BTreeMap<String, String>,
    pub auth_by_package: BTreeMap<String, Auth>,
}

impl Default for EndpointDefaults {
    fn default() -> Self {
        serde_json::from_str(include_str!("data/avp_endpoint_defaults.json"))
            .expect("bundled endpoint defaults are valid")
    }
}

pub fn bundled_endpoints() -> Endpoints {
    serde_json::from_str(include_str!("data/avp_endpoints.json"))
        .expect("bundled endpoints are valid")
}

pub fn default_cache_path() -> PathBuf {
    models_dev::cache_path(FILE)
}

pub fn fetch_endpoints(catalog: Option<&Value>) -> Result<Endpoints> {
    fetch_endpoints_with(catalog, &EndpointDefaults::default())
}

/// Build endpoints with caller-supplied URL fallbacks and package auth rules.
pub fn fetch_endpoints_with(
    catalog: Option<&Value>,
    defaults: &EndpointDefaults,
) -> Result<Endpoints> {
    let catalog = models_dev::catalog(catalog)?;
    let mut providers = BTreeMap::new();
    for (id, provider) in catalog.as_object().ok_or("catalog must be an object")? {
        let base_url = provider
            .get("api")
            .and_then(Value::as_str)
            .filter(|api| !api.is_empty() && !api.contains("${"))
            .map(String::from)
            .or_else(|| defaults.gap_fillers.get(id).cloned());
        let auth = provider
            .get("npm")
            .and_then(Value::as_str)
            .and_then(|package| defaults.auth_by_package.get(package))
            .cloned();
        if base_url.as_ref().is_some_and(|url| !url.is_empty()) || auth.is_some() {
            providers.insert(id.clone(), Endpoint { base_url, auth });
        }
    }
    Ok(Endpoints {
        source: models_dev::source(),
        fetched: Utc::now(),
        providers,
    })
}

pub fn save_endpoints(endpoints: &Endpoints, path: Option<&Path>) -> Result<PathBuf> {
    models_dev::save(
        endpoints,
        &path
            .map(Path::to_path_buf)
            .unwrap_or_else(default_cache_path),
    )
}

/// Offline unless `max_age` requests a refresh; otherwise prefer the newer cache or bundle.
pub fn load_endpoints(path: Option<&Path>, max_age: Option<Duration>) -> Result<Endpoints> {
    models_dev::load(
        path,
        &default_cache_path(),
        max_age,
        bundled_endpoints,
        || fetch_endpoints(None),
    )
}

pub fn default_base_url<'a>(endpoints: &'a Endpoints, provider: &str) -> Option<&'a str> {
    endpoints.providers.get(provider)?.base_url.as_deref()
}

pub fn provider_auth<'a>(endpoints: &'a Endpoints, provider: &str) -> Option<&'a Auth> {
    endpoints.providers.get(provider)?.auth.as_ref()
}

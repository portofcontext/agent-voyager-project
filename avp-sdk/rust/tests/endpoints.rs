use avp::utils::endpoints::{
    Auth, EndpointDefaults, Endpoints, bundled_endpoints, default_base_url, fetch_endpoints,
    fetch_endpoints_with, load_endpoints, provider_auth, save_endpoints,
};
use chrono::Utc;
use serde_json::{Value, json};
use std::fs;

#[test]
fn catalog_conversion_follows_the_shared_python_cases() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("../../testdata/endpoints/catalog.json")).unwrap();
    for case in cases {
        let mut defaults = EndpointDefaults::default();
        if let Some(fill) = case.get("fill") {
            defaults.gap_fillers = serde_json::from_value(fill.clone()).unwrap();
        }
        if let Some(auth) = case.get("auth") {
            defaults.auth_by_package = serde_json::from_value(auth.clone()).unwrap();
        }
        let fetched = fetch_endpoints_with(Some(&case["catalog"]), &defaults).unwrap();
        assert_eq!(
            serde_json::to_value(fetched).unwrap()["providers"],
            case["providers"],
            "{}",
            case["name"]
        );
    }
    // The default public entry point uses the same shared rules.
    let fetched =
        fetch_endpoints(Some(&json!({"anthropic": {"npm": "@ai-sdk/anthropic"}}))).unwrap();
    assert_eq!(
        provider_auth(&fetched, "anthropic").unwrap().header,
        "x-api-key"
    );
}

#[test]
fn bundled_defaults_cover_api_key_schemes_without_guessing_dynamic_auth() {
    let endpoints = bundled_endpoints();
    assert_eq!(
        default_base_url(&endpoints, "anthropic"),
        Some("https://api.anthropic.com/v1")
    );
    assert_eq!(
        default_base_url(&endpoints, "openrouter"),
        Some("https://openrouter.ai/api/v1")
    );
    assert_eq!(default_base_url(&endpoints, "amazon-bedrock"), None);
    for (provider, header, prefix) in [
        ("anthropic", "x-api-key", ""),
        ("google", "x-goog-api-key", ""),
        ("openrouter", "authorization", "Bearer "),
        ("amazon-bedrock", "authorization", "Bearer "),
    ] {
        assert_eq!(
            provider_auth(&endpoints, provider),
            Some(&Auth {
                header: header.into(),
                prefix: prefix.into()
            })
        );
    }
    for provider in ["google-vertex", "unknown"] {
        assert_eq!(provider_auth(&endpoints, provider), None);
    }
}

#[test]
fn explicit_endpoint_cache_round_trips_offline_and_rejects_corruption() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("nested/endpoints.json");
    assert!(load_endpoints(Some(&path), None).is_err());
    let snapshot = bundled_endpoints();
    save_endpoints(&snapshot, Some(&path)).unwrap();
    assert_eq!(load_endpoints(Some(&path), None).unwrap(), snapshot);
    assert!(!path.with_file_name(".endpoints.json.partial").exists());
    for endpoint in [
        json!({"extra": true}),
        json!({"auth": {"prefix": "Bearer "}}),
        json!({"auth": {"header": 1}}),
    ] {
        fs::write(
            &path,
            json!({"fetched": Utc::now(), "providers": {"test": endpoint}}).to_string(),
        )
        .unwrap();
        assert!(load_endpoints(Some(&path), None).is_err());
    }
    fs::write(
        &path,
        json!({"fetched": Utc::now(), "providers": {"test": {"auth": {"header": "x-key"}}}})
            .to_string(),
    )
    .unwrap();
    assert_eq!(
        provider_auth(&load_endpoints(Some(&path), None).unwrap(), "test")
            .unwrap()
            .prefix,
        ""
    );
    fs::write(&path, "broken JSON").unwrap();
    assert!(load_endpoints(Some(&path), None).is_err());
    assert!(
        serde_json::from_value::<Endpoints>(json!({"fetched": "no date", "providers": {}}))
            .is_err()
    );
}

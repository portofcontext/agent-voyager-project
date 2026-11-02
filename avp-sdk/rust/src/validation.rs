use std::{
    collections::HashMap,
    sync::{LazyLock, Mutex},
};

use serde_json::{Value, json};

static SCHEMA: LazyLock<Value> =
    LazyLock::new(|| serde_json::from_str(include_str!("schemas/trajectory.json")).unwrap());
static VALIDATORS: LazyLock<Mutex<HashMap<String, jsonschema::Validator>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

pub(crate) fn event_name(kind: &str) -> Option<&'static str> {
    SCHEMA
        .get("discriminator")?
        .get("mapping")?
        .get(kind)?
        .as_str()?
        .rsplit('/')
        .next()
}

pub(crate) fn validate(name: &str, value: &Value) -> crate::Result<()> {
    let mut normalized;
    let value = if name == "ErrorOccurred" || name == "ErrorOccurredEvent" {
        normalized = value.clone();
        let pointer = if name == "ErrorOccurred" {
            "/error_code"
        } else {
            "/data/error_code"
        };
        if let Some(code) = normalized
            .pointer_mut(pointer)
            .filter(|code| code.is_string())
        {
            let known: crate::trajectory::ErrorCode = serde_json::from_value(code.clone())?;
            *code = serde_json::to_value(known)?;
        }
        &normalized
    } else {
        value
    };
    let mut validators = VALIDATORS.lock().unwrap();
    if !validators.contains_key(name) {
        let schema = json!({"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"],
            "$ref": format!("#/$defs/{name}")});
        validators.insert(
            name.into(),
            jsonschema::options()
                .should_validate_formats(true)
                .build(&schema)?,
        );
    }
    validators[name]
        .validate(value)
        .map_err(|e| e.to_string().into())
}

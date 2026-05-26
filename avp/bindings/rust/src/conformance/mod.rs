//! Conformance-harness fixture types and SDK-author utilities.
//!
//! Not part of the wire spec. Mirrors `avp.conformance` in the Python
//! reference package: parse a CLI arg that's either inline JSON or a path,
//! and deserialize it into the wire types an SDK's
//! `run --commission <json|path> [--built-in <json|path>]` entrypoint consumes.

pub mod agent_builtins;

pub use agent_builtins::AgentBuiltins;

use std::fs;

use serde_json::Value;

use crate::Commission;

/// Errors from loading a JSON arg or deserializing it into a wire type.
#[derive(Debug)]
pub enum LoadError {
    Io(std::io::Error),
    Json(serde_json::Error),
}

impl std::fmt::Display for LoadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "i/o error: {e}"),
            Self::Json(e) => write!(f, "json error: {e}"),
        }
    }
}

impl std::error::Error for LoadError {}

impl From<std::io::Error> for LoadError {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e)
    }
}

impl From<serde_json::Error> for LoadError {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e)
    }
}

/// Parse a CLI arg that accepts either inline JSON or a path to a JSON file.
///
/// Inline JSON is detected by a leading `{` or `[` after whitespace; anything
/// else is treated as a path and read from disk.
pub fn read_json_arg(value: &str) -> Result<Value, LoadError> {
    let trimmed = value.trim();
    if trimmed.starts_with('{') || trimmed.starts_with('[') {
        Ok(serde_json::from_str(trimmed)?)
    } else {
        let text = fs::read_to_string(trimmed)?;
        Ok(serde_json::from_str(&text)?)
    }
}

/// Load and deserialize a [`Commission`] from inline JSON or a path.
pub fn load_commission(value: &str) -> Result<Commission, LoadError> {
    Ok(serde_json::from_value(read_json_arg(value)?)?)
}

/// Load and deserialize an [`AgentBuiltins`] fixture from inline JSON or a path.
pub fn load_built_in(value: &str) -> Result<AgentBuiltins, LoadError> {
    Ok(serde_json::from_value(read_json_arg(value)?)?)
}

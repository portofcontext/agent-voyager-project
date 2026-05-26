//! Derive the resolved `goose` dependency version from Cargo.lock and expose it
//! as the `GOOSE_VERSION` compile-time env var (used as the descriptor's
//! `agent_version`), so it tracks the dependency instead of a hardcode.

use std::{env, fs, path::Path};

fn main() {
    let lock = Path::new(&env::var("CARGO_MANIFEST_DIR").unwrap()).join("Cargo.lock");
    println!("cargo:rerun-if-changed=Cargo.lock");
    let version = fs::read_to_string(&lock)
        .ok()
        .and_then(|contents| goose_version(&contents))
        .unwrap_or_else(|| "unknown".to_string());
    println!("cargo:rustc-env=GOOSE_VERSION={version}");
}

/// Find `version` in the `[[package]]` block whose `name = "goose"`. Cargo.lock
/// lists `name` before `version` within each block.
fn goose_version(lock: &str) -> Option<String> {
    let mut in_goose = false;
    for line in lock.lines() {
        let line = line.trim();
        if line == "[[package]]" {
            in_goose = false;
        } else if line == "name = \"goose\"" {
            in_goose = true;
        } else if in_goose {
            if let Some(rest) = line.strip_prefix("version = ") {
                return Some(rest.trim_matches('"').to_string());
            }
        }
    }
    None
}

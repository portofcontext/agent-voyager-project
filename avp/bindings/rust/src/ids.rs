//! CloudEvents / OTel id and timestamp helpers.
//!
//! An agent that emits a trajectory stamps every event's envelope (`id`,
//! `time`) and span identity (`trace_id`, `span_id`, `parent_span_id`) with
//! these.

use chrono::{SecondsFormat, Utc};
use uuid::Uuid;

/// OTel "absent parent" sentinel: 16 zero hex chars. Use as `parent_span_id`
/// for a top-level (root) span.
pub const ZERO_SPAN_ID: &str = "0000000000000000";

/// CloudEvents `source` for every AVP event. The agent is the sole producer
/// on the wire; supervisor attribution rides inside `run_requested.data`.
pub const SOURCE_AGENT: &str = "avp://agent";

/// ISO 8601 / RFC 3339 timestamp with a `Z` suffix (UTC).
pub fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true)
}

/// CloudEvents `id`: a UUID v4, unique within `source`.
pub fn new_event_id() -> String {
    Uuid::new_v4().to_string()
}

/// OTel trace id: 16 random bytes, hex-encoded (32 lowercase chars).
pub fn new_trace_id() -> String {
    hex(Uuid::new_v4().as_bytes())
}

/// OTel span id: 8 random bytes, hex-encoded (16 lowercase chars).
pub fn new_span_id() -> String {
    hex(&Uuid::new_v4().as_bytes()[..8])
}

fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write;
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        let _ = write!(s, "{b:02x}");
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trace_id_is_32_lowercase_hex() {
        let t = new_trace_id();
        assert_eq!(t.len(), 32);
        assert!(t
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
    }

    #[test]
    fn span_id_is_16_lowercase_hex() {
        let s = new_span_id();
        assert_eq!(s.len(), 16);
        assert!(s
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
        assert_eq!(ZERO_SPAN_ID.len(), s.len());
    }

    #[test]
    fn event_id_is_uuid_and_unique() {
        let a = new_event_id();
        assert_eq!(a.len(), 36); // 8-4-4-4-12
        assert_ne!(a, new_event_id());
    }

    #[test]
    fn now_iso_is_utc_z() {
        assert!(now_iso().ends_with('Z'));
    }
}

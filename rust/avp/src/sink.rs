//! Trajectory event sink.
//!
//! A [`Sink`] is where every emitted trajectory event leaves the agent; the
//! agent owns the run lifecycle, the sink owns serialization and I/O.
//! Transport (stdout, file, websocket, OTLP) is the sink's concern.
//!
//! Emission is synchronous: serializing one event and writing a line is cheap,
//! and a sync trait stays object-safe (`Box<dyn Sink>` / `Arc<dyn Sink>`).
//! Sinks needing async or shared mutable state use interior mutability.

use std::io::{self, Write};

use crate::Event;

/// Consumes one trajectory event at a time. Serde already emits the canonical
/// wire form (dotted alias keys, `None` fields omitted), so implementations
/// serialize the [`Event`] directly.
pub trait Sink {
    fn emit(&self, event: &Event) -> io::Result<()>;
}

/// Built-in sink: one event per line of NDJSON to stdout. Convenient for local
/// runs, examples, and conformance smoke tests.
pub struct StdioSink;

impl Sink for StdioSink {
    fn emit(&self, event: &Event) -> io::Result<()> {
        let line = serde_json::to_string(event).map_err(io::Error::other)?;
        let mut out = io::stdout().lock();
        out.write_all(line.as_bytes())?;
        out.write_all(b"\n")?;
        out.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    #[derive(Default)]
    struct CapturingSink {
        lines: Mutex<Vec<String>>,
    }

    impl Sink for CapturingSink {
        fn emit(&self, event: &Event) -> io::Result<()> {
            let line = serde_json::to_string(event).map_err(io::Error::other)?;
            self.lines.lock().unwrap().push(line);
            Ok(())
        }
    }

    const AGENT_STOPPED: &str = r#"{
        "specversion": "1.0",
        "id": "test-id",
        "time": "2026-05-07T00:00:00Z",
        "subject": "r1",
        "datacontenttype": "application/json",
        "type": "avp.agent_stopped",
        "source": "avp://agent",
        "data": {
            "trace_id": "00000000000000000000000000000000",
            "span_id": "2222222222222222",
            "parent_span_id": "0000000000000000",
            "avp.reason": "refused"
        }
    }"#;

    #[test]
    fn emits_one_ndjson_line_with_type_tag() {
        let ev: Event = serde_json::from_str(AGENT_STOPPED).unwrap();
        let sink = CapturingSink::default();
        sink.emit(&ev).unwrap();
        let lines = sink.lines.lock().unwrap();
        assert_eq!(lines.len(), 1);
        // Tagged union: `type` is on the wire and the value round-trips.
        assert!(lines[0].contains(r#""type":"avp.agent_stopped""#));
        // NDJSON invariant: the serialized event is a single line.
        assert!(!lines[0].contains('\n'));
    }
}

//! Trajectory event sink.
//!
//! A [`Sink`] is where every emitted trajectory event leaves the agent; the
//! agent owns the run lifecycle, the sink owns serialization and I/O.
//! Transport (stdout, file, websocket, OTLP) is the sink's concern.
//!
//! Emission is synchronous: serializing one event and writing a line is cheap,
//! and a sync trait stays object-safe (`Box<dyn Sink>` / `Arc<dyn Sink>`).
//! Sinks needing async or shared mutable state use interior mutability.

use std::fs::File;
use std::io::{self, Write};
use std::path::Path;
use std::sync::Mutex;

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

/// Built-in sink: one event per line of NDJSON to a file. The file is
/// truncated on construction, then each event is written and flushed in
/// emission order, so a concurrent reader (`tail -f`) sees progress without
/// waiting for the agent to finish. This is what satisfies the conformance
/// `run --out <path.jsonl>` contract; the Python counterpart is
/// `avp.sink.jsonl_sink`.
pub struct FileSink {
    file: Mutex<File>,
}

impl FileSink {
    /// Create (truncating any existing file) the sink at `path`.
    pub fn create(path: impl AsRef<Path>) -> io::Result<Self> {
        Ok(Self {
            file: Mutex::new(File::create(path)?),
        })
    }
}

impl Sink for FileSink {
    fn emit(&self, event: &Event) -> io::Result<()> {
        let line = serde_json::to_string(event).map_err(io::Error::other)?;
        let mut file = self.file.lock().expect("FileSink mutex poisoned");
        file.write_all(line.as_bytes())?;
        file.write_all(b"\n")?;
        file.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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

    #[test]
    fn file_sink_truncates_then_appends_one_line_per_event() {
        let ev: Event = serde_json::from_str(AGENT_STOPPED).unwrap();
        let path = std::env::temp_dir().join(format!("avp-filesink-{}.jsonl", std::process::id()));
        std::fs::write(&path, b"stale\n").unwrap(); // pre-existing content

        let sink = FileSink::create(&path).unwrap();
        sink.emit(&ev).unwrap();
        sink.emit(&ev).unwrap();

        let body = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = body.lines().collect();
        // Truncated on create (no "stale"), one NDJSON line per emit.
        assert_eq!(lines.len(), 2);
        assert!(lines.iter().all(|l| l.contains(r#""type":"avp.agent_stopped""#)));
        std::fs::remove_file(&path).ok();
    }
}

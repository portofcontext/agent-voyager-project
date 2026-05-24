//! Shared helpers for the crate's unit tests. (Integration tests have their own
//! richer harness in `tests/common`; this is the in-crate equivalent for the
//! `#[cfg(test)]` modules that drive the emitter / run-state directly.)

use std::sync::{Arc, Mutex};

use avp::sink::Sink;
use avp::Event;
use serde_json::Value;

/// A sink that captures emitted events as wire-form JSON for assertions.
#[derive(Clone, Default)]
pub(crate) struct CapturingSink {
    pub events: Arc<Mutex<Vec<Value>>>,
}

impl Sink for CapturingSink {
    fn emit(&self, event: &Event) -> std::io::Result<()> {
        self.events
            .lock()
            .unwrap()
            .push(serde_json::to_value(event).unwrap());
        Ok(())
    }
}

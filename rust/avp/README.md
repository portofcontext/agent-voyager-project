# avp — Rust types for the AVP wire format

```toml
[dependencies]
avp = { git = "https://github.com/portofcontext/agent-execution-protocol" }
```

(Not yet on crates.io. Vendor by git path until v0.1 stabilizes.)

## What's here

Generated Rust types for the AVP v0.1 wire format. Three modules, one per top-level message class:

```rust
use avp::{Commission, Event, SupervisorMessage};

let event: Event = serde_json::from_str(line)?;
match event {
    Event::AgentStartedEvent(_) => { /* ... */ }
    Event::ModelTurnEndedEvent(e) => {
        let cost = e.data.avp_cost_usd;
        let source = e.data.avp_cost_source;  // "computed" | "reported" | "unknown"
    }
    Event::RefusalRecordedEvent(e) => { /* ... */ }
    // ...
}
```

Use `avp::config`, `avp::event`, `avp::supervisor_message` for the helper data types (the per-event `*Data` structs, `JsonRpcRequestPayload`, `Verifier`, etc.).

## Source of truth

- `python/avp/src/avp/types.py` (Pydantic, hand-written)
  → `spec/v0.1/*.schema.json` (auto-generated; `scripts/generate-schemas.py`)
  → `rust/avp/src/*.rs` (generated here, via `cargo-typify`)

Don't edit `src/{config,event,supervisor_message}.rs` by hand — they're regenerated. Edit `types.py` upstream.

## Regenerating

```bash
make bindings           # regenerate from current schemas
make bindings-check     # CI drift check (fails if generated code is stale)
make bindings-test      # smoke tests for both Rust and TS
```

## Known shape quirks

- **Newtype wrappers everywhere.** typify generates `pub struct AepApprovalId(String)` and similar one-line wrappers per nullable string. Use `.0` or `Deref` to get the inner value. Verbose but type-safe.
- **`Subject`, `Id`, etc. are duplicated per event variant.** typify can't deduplicate identical types across schema definitions. They're equivalent on the wire; the duplication is a code-size wart, not a correctness problem.
- **Helper types repeat across modules.** `JsonRpcRequestPayload` exists in both `event` and `supervisor_message` because typify can't follow `$ref` across schema files. Pick the module-scoped one matching what you're deserializing.

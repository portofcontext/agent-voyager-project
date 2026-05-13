# avp — Rust types for the AVP wire format

```toml
[dependencies]
avp = { git = "https://github.com/portofcontext/agent-voyager-project" }
```

(Not yet on crates.io. Vendor by git path until v0.1 stabilizes.)

## What's here

Generated Rust types for the AVP v0.1 wire format. Two modules, one per top-level message class:

```rust
use avp::{Commission, Event};

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

Use `avp::commission`, `avp::trajectory`, and `avp::agent_descriptor` for the helper data types (the per-event `*Data` structs, the `AgentDescriptor` shape, etc.).

## Source of truth

- `python/avp/src/avp/{commission,descriptor,trajectory}.py` (Pydantic, hand-written)
  → `spec/v0.1/*.schema.json` (auto-generated; `scripts/generate-schemas.py`)
  → `rust/avp/src/*.rs` (generated here, via `cargo-typify`)

Don't edit `src/{commission,event}.rs` by hand — they're regenerated. Edit the Python sources upstream.

## Regenerating

```bash
make bindings           # regenerate from current schemas
make bindings-check     # CI drift check (fails if generated code is stale)
make bindings-test      # smoke tests for both Rust and TS
```

## Known shape quirks

- **Newtype wrappers everywhere.** typify generates `pub struct AvpApprovalId(String)` and similar one-line wrappers per nullable string. Use `.0` or `Deref` to get the inner value. Verbose but type-safe.
- **`Subject`, `Id`, etc. are duplicated per event variant.** typify can't deduplicate identical types across schema definitions. They're equivalent on the wire; the duplication is a code-size wart, not a correctness problem.
- **Helper types repeat across modules.** Some helper structs are duplicated across `commission` and `event` because typify can't follow `$ref` across schema files. Pick the module-scoped one matching what you're deserializing.

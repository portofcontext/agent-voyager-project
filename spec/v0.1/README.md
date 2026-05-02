# AEP Spec — v0.1

This directory is the **normative specification** for the Agent Execution Protocol, version 0.1.

## Layout

| File | Purpose |
|---|---|
| [`SPEC.md`](./SPEC.md) | Normative prose. RFC 2119 keywords. Reference algorithm for the runner loop. Conformance criteria for runners and supervisors. |
| [`aep.schema.json`](./aep.schema.json) | Bundled JSON Schema (Draft 2020-12). All type definitions in `$defs`; top-level `oneOf` over Config / Event / SupervisorMessage. |
| [`config.schema.json`](./config.schema.json) | Entry-point schema for the supervisor → runner Config. |
| [`event.schema.json`](./event.schema.json) | Entry-point schema for one event in the canonical trajectory (either source). |
| [`supervisor-message.schema.json`](./supervisor-message.schema.json) | Entry-point schema for messages the supervisor sends to the runner. |
| [`examples/`](./examples/) | Conforming fixtures referenced by `SPEC.md`. |

The three entry-point schemas all `$ref` into `aep.schema.json#/$defs/...`. Validators MUST resolve `$ref` against the `$id` URIs (or use a local `$id` → file mapping when validating offline).

## Schema dialect

[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/release-notes). Tested with `python-jsonschema` ≥ 4.18 and `ajv` (with `ajv-formats`).

## Versioning

The `$id` and `Config.schema_version` are versioned together. Future versions live in sibling directories; published schemas are immutable.

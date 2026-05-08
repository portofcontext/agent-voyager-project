# AVP Spec — v0.1

This directory is the **normative specification** for the Agent Voyage Protocol, version 0.1.

## Layout

| File | Purpose |
|---|---|
| [`SPEC.md`](./SPEC.md) | Normative prose. RFC 2119 keywords. Reference algorithm for the agent loop. Conformance criteria for agents and supervisors. |
| [`avp.schema.json`](./avp.schema.json) | Bundled JSON Schema (Draft 2020-12). All type definitions in `$defs`; top-level `oneOf` over Commission / Event / SupervisorMessage. |
| [`commission.schema.json`](./commission.schema.json) | Entry-point schema for the supervisor → agent Commission. |
| [`event.schema.json`](./event.schema.json) | Entry-point schema for one event in the canonical trajectory (either source). |
| [`supervisor-message.schema.json`](./supervisor-message.schema.json) | Entry-point schema for messages the supervisor sends to the agent. |
| [`examples/`](./examples/) | Conforming fixtures referenced by `SPEC.md`. |

The three entry-point schemas all `$ref` into `avp.schema.json#/$defs/...`. Validators MUST resolve `$ref` against the `$id` URIs (or use a local `$id` → file mapping when validating offline).

## Schema dialect

[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/release-notes). Tested with `python-jsonschema` ≥ 4.18 and `ajv` (with `ajv-formats`).

## Versioning

The `$id` and `Commission.schema_version` are versioned together. Future versions live in sibling directories; published schemas are immutable.

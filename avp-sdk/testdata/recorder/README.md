# Recorder test cases

Every SDK's Recorder passes these cases. Each file is one case:

| Field | What it holds |
|---|---|
| `name`, `description` | What the case shows. |
| `prices` | The models.dev prices to compute costs with, keyed `<provider>/<model id>`. |
| `calls` | The Recorder calls to make, in order. |
| `trajectory` | The completed native ATIF document. |

Each call has `call`, the Recorder method in snake_case, and its arguments by
name. `t` is the clock, in milliseconds after the start, while the call runs.
`raises: true` means the call must raise the Recorder's error and write nothing.

Run each case with a Recorder whose `run_id` is `run-0`. Validate every
published snapshot as ATIF, then compare the final document to `trajectory`:

- Compare timestamps as instants, independent of UTC spelling.
- Omit unset optional ATIF fields; preserve explicit nulls in open JSON objects.
- Compare numbers with a relative tolerance of 1e-9.
- `"<any>"` matches text whose wording may differ between SDKs.

The expected documents were captured independently from the previous ATIF
converter before replacing it with native recording. They cover streaming,
parallel tools, nested children, opaque child accounting, partial usage,
interruption, invalid input, and structured output.

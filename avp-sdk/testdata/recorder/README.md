# Recorder test cases

Every SDK's Recorder passes these cases. Each file is one case:

| Field | What it holds |
|---|---|
| `name`, `description` | What the case shows. |
| `prices` | The models.dev prices to compute costs with, keyed `<provider>/<model id>`. |
| `calls` | The Recorder calls to make, in order. |
| `trajectory` | The ATIF document the Recorder writes. |
| `files` | The paths of the files written beside it, when there are any. |

Each call has `call`, the Recorder method in snake_case, and its arguments by
name. `agent` is ATIF JSON. A step's `parts` are the
Recorder's part types as JSON, each with its `type`: `text`, `reasoning`,
`call`, or `server_result`. `usage`, on a step or a stopped subagent, is the Recorder's usage type as JSON. `t` is the clock, in milliseconds
after the start, while the call runs. `raises: true` means the call must raise
the Recorder's error and record nothing.

Run each case with a Recorder whose `run_id` is `run-0`. The Recorder must
write exactly one document. Compare it to `trajectory`:

- Compare timestamps as instants, independent of UTC spelling.
- Omit unset optional fields; keep explicit nulls.
- Compare numbers with a relative tolerance of 1e-9.
- `"<any>"` matches text whose wording may differ between SDKs.

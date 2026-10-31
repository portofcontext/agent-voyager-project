# Recorder test cases

Every SDK's Recorder passes these cases. Each file is one case:

| Field | What it holds |
|---|---|
| `name`, `description` | What the case shows. |
| `prices` | The models.dev prices to compute costs with, keyed `<provider>/<model id>`. |
| `calls` | The Recorder calls to make, in order. |
| `events` | The events the Recorder must write. |

Each call has `call`, the Recorder method in snake_case, and its arguments by
name. `t` is the clock, in milliseconds after the start, while the call runs.
`raises: true` means the call must raise the Recorder's error and write nothing.

Run each case with a Recorder whose `run_id` is `run-0`. Compare the events it
writes, in order, after these changes:

- Drop `id`, after checking that no two events share one.
- Replace `time` with `t`, in milliseconds after the start.
- Leave out fields that are absent or null.
- Compare numbers as numbers, with a relative tolerance of 1e-9.
- `"<any>"` matches any string. It stands for text an SDK words its own way,
  such as why a Commission doesn't match the spec.

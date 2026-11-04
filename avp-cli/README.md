# avp

The `avp` command line: run, evaluate, and check AVP agents in sandboxes. The
design is in [COMMANDS.md](COMMANDS.md).

## Commissions

```sh
avp commission new --agent pd --model anthropic/claude-haiku-4-5 --prompt "Say hello" > task.json
avp commission check task.json --agent pd
avp commission save hello task.json
avp run --commission hello --agent pd
avp commission list
avp commission delete hello --yes
```

`pd` is an installed agent name. `run --commission` also accepts a file path.
See [Commission commands](COMMANDS.md#commissions) for names, validation, and
per-run identity. Saved Commissions also work in [eval files](docs/eval.md).

## Development

From this directory:

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

`tests/test_agent.py` and `tests/test_conformance_mock.py` start real sandboxes.
They skip when no container engine answers. On macOS, point `TMPDIR` at a
directory shared with the container engine so bind mounts reach test files.

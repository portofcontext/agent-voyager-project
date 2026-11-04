# avp

The `avp` command line: run, evaluate, and check AVP agents in sandboxes. The
design is in [COMMANDS.md](COMMANDS.md).

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

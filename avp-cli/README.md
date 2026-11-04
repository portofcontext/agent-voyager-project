# avp

The `avp` command line: run, evaluate, and check AVP agents in sandboxes. The
design is in [COMMANDS.md](COMMANDS.md). The old CLI is in
[`avp-cli-legacy/`](../avp-cli-legacy/), for reference only.

## Development

From this directory:

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

`tests/test_agent.py` builds images and starts sandboxes. It is skipped when no
container engine answers.

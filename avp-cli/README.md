# avp

The `avp` command line: run, evaluate, and check AVP agents in sandboxes. The
design is in [COMMANDS.md](COMMANDS.md).

## Install

```sh
uv tool install https://github.com/portofcontext/agent-voyager-project/releases/download/cli-v0.6.0b2/avp_cli-0.6.0b2-py3-none-any.whl
```

## Agents

```sh
avp agent list --builtin
avp agent install pydantic-ai
avp agent ping pydantic-ai
```

A running Docker or podman engine is required. The CLI downloads the pinned
source and builds the agent image. No checkout is needed.

## Commissions

```sh
avp commission new --agent pydantic-ai --model anthropic/claude-haiku-4-5 --prompt "Say hello" > task.json
avp commission check task.json --agent pydantic-ai
avp commission save hello task.json
avp run --commission hello --agent pydantic-ai
avp commission list
avp commission delete hello --yes
```

`pydantic-ai` is the installed agent name. `run --commission` also accepts a file path.
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

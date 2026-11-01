# AVP Python SDK

The Python SDK for the [AVP v0.1 specs](../../spec/v0.1/). Its scope is in the
[SDK working doc](../README.md).

The import package is `avp`. The distribution is named `agent-voyager-project`
because `avp` on PyPI is an unrelated project.

## Development

From this directory:

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

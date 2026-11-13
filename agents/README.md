# Agent development

Each agent is an independent project. Its package file and lockfile pin a
published SDK beta. The CLI ships its Dockerfile and installs it by name:

```sh
avp agent list --builtin
avp agent install pydantic-ai
```

To build local agent changes, use a custom name and the agent's directory as
context, from the repository root:

```sh
avp agent install my-pydantic-ai avp-cli/src/avp_cli/agents/dockerfiles/pydantic-ai.Dockerfile --context agents/avp-pydantic-ai/python
```

## Updating built-in agents

`avp-cli/src/avp_cli/agents/builtins.json` pins a source commit, its GitHub archive's
SHA-256, and each agent's package version and directory. Dockerfiles live beside
it in `dockerfiles/`. To upgrade, commit and push the agent changes first, update
the source pin and checksum, and update the packaged Dockerfiles.
Check that each declared version matches the agent package at that commit.
Run the checks, bump the CLI version, and publish a new CLI beta. Published
CLI versions keep their pins.

## Local SDK development

Adapters use the SDK source from this repository. Python's `tool.uv.sources`
links the matching SDK; TypeScript uses a relative file dependency. Built-in
Docker builds use the repository root and bundle the SDK at the same source pin.
This avoids mixing a new adapter wire contract with an older published SDK.

For Python, run `uv sync --locked` and `uv run pytest` in the adapter's `python/`
directory. For TypeScript, build the SDK first, then the adapter:

```sh
npm --prefix avp-sdk/typescript ci
npm --prefix avp-sdk/typescript run build
npm --prefix agents/avp-pi/typescript ci
npm --prefix agents/avp-pi/typescript test
```

The `make` adapter targets build their SDK dependency automatically.

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

For Python, run from the agent's `python/` directory:

```sh
uv sync --locked
uv run --with-editable ../../../avp-sdk/python pytest
```

The temporary override uses the local SDK without changing the package file or
lockfile. Run `uv run pytest` to use the released SDK again.

For TypeScript, build the local SDK, then install it temporarily from the agent's
`typescript/` directory:

```sh
npm --prefix ../../../avp-sdk/typescript ci
npm --prefix ../../../avp-sdk/typescript run build
npm ci
npm install --no-save --package-lock=false ../../../avp-sdk/typescript
npm test
```

Run `npm ci` to restore the released SDK. Commit dependencies on published
packages; keep local overrides out of package files and lockfiles.

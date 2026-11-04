# Agent development

Each agent is an independent project. Its package file and lockfile pin a
published SDK beta. Build its sandbox image with the agent's language directory
as the context; the repository's SDK source is not needed.

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

# Agent development

Each adapter is a separate package. In the repository it uses the local SDK;
a released package declares an SDK version range. See the
[release guide](../docs/releases/README.md) for publishing and installation.

## Local SDK development

Python's `[tool.uv.sources]` links the SDK source. Run `uv sync --locked` and
`uv run pytest` in the adapter's `python/` directory.

TypeScript uses the root npm workspaces and lockfile. From the repository root:

```sh
npm ci --ignore-scripts
make pi-check
make gemini-cli-check
make opencode-check
```

The make targets build the SDK before the adapter. Published npm packages
contain compiled code and a version-range dependency, without workspace paths.

## Built-in agents

The CLI's Dockerfiles install pinned released adapter and SDK packages without
a repository build context. `builtins.json` records package versions and image
digests. Update both the catalog and Dockerfile when releasing an adapter.

To exercise unreleased code in a container, write a temporary Dockerfile in a
test or script with the repository root as its context. Keep development image
recipes outside the CLI package.

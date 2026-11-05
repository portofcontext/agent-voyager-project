# Beta packages

SDKs and the CLI are published as GitHub prereleases. Each release contains
the package, a `release.json` manifest, and `SHA256SUMS`.

## Install

Python SDK:

```sh
uv pip install https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-python-v0.1.0b2/agent_voyager_project-0.1.0b2-py3-none-any.whl
```

TypeScript SDK:

```sh
npm install https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-typescript-v0.1.0-beta.2/agent-voyager-project-sdk-0.1.0-beta.2.tgz
```

CLI (includes the SDK dependency):

```sh
uv tool install https://github.com/portofcontext/agent-voyager-project/releases/download/cli-v0.7.0/avp_cli-0.7.0-py3-none-any.whl
avp --help
```

`avp update` installs the newest CLI release over the one you have.

Use these URLs to install the beta. `pip install avp-cli` installs the release
on PyPI, currently 0.5.0. The beta is distributed through GitHub.

## Publish

Set the version in the package's `pyproject.toml` or `package.json` and update
its lockfile. Python uses `0.1.0b2`; npm uses `0.1.0-beta.2`.
Before an SDK release, run `make sdk-data` and commit the refreshed snapshots.
Run `make check`, commit the changes, and push the branch.

From the clean, pushed branch:

```sh
make release-sdk-python
make release-sdk-typescript
# Wait for the SDK releases before publishing the CLI that depends on them.
make release-cli
```

Each target creates and pushes an annotated tag using the package version.
The GitHub Packages workflow tests the code, builds the package, installs it
in a clean environment, then publishes the release. Existing tags are never
overwritten. Bump the version for another release.

### Built-in agent images

The CLI installs built-in agents from images at
`ghcr.io/portofcontext/<agent_name>:<version>`, pinned by digest in
`avp-cli/src/avp_cli/agents/builtins.json`. Before a CLI release that changes
the source commit or an agent's version there:

1. Push the branch, then run the Agent images workflow on it. It builds each
   agent from the pinned commit for amd64 and arm64, and leaves a version that
   is already published as it is. Bump an agent's version to publish it again.
2. A new package starts private. Make it public in the organization's package
   settings, once per agent.
3. Run `make agent-images` to write the digests to `builtins.json`, and commit.

An agent without an `image` there installs by building from the pinned source.

Tags are `sdk-python-v<version>`, `sdk-typescript-v<version>`, and `cli-v<version>`.
Beta tags can be cut from the release branch before it merges into `main`.

To build and install-check an artifact locally:

```sh
python scripts/release.py build sdk-python --out /tmp/avp-sdk-release
```

The output directory must be empty. `build` accepts `sdk-python`,
`sdk-typescript`, and `cli`.


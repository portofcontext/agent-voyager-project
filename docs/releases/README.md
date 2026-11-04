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
uv tool install https://github.com/portofcontext/agent-voyager-project/releases/download/cli-v0.6.0b2/avp_cli-0.6.0b2-py3-none-any.whl
avp --help
```

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

Tags are `sdk-python-v<version>`, `sdk-typescript-v<version>`, and `cli-v<version>`.
Beta tags can be cut from the release branch before it merges into `main`.

To build and install-check an artifact locally:

```sh
python scripts/release.py build sdk-python --out /tmp/avp-sdk-release
```

The output directory must be empty. `build` accepts `sdk-python`,
`sdk-typescript`, and `cli`.


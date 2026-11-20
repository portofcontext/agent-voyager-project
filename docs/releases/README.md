# Beta packages

SDKs, adapters, and the CLI are published as GitHub prereleases. Each release
contains its package, a `release.json` manifest, and `SHA256SUMS`. The manifest
names the released SDK artifact a dependent package needs.

## Install

Python SDK:

```sh
uv pip install https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-python-v0.1.0b3/agent_voyager_project-0.1.0b3-py3-none-any.whl
```

TypeScript SDK:

```sh
npm install https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-typescript-v0.1.0-beta.3/agent-voyager-project-sdk-0.1.0-beta.3.tgz
```

CLI:

```sh
uv tool install --with https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-python-v0.1.0b3/agent_voyager_project-0.1.0b3-py3-none-any.whl https://github.com/portofcontext/agent-voyager-project/releases/download/cli-v0.8.1/avp_cli-0.8.1-py3-none-any.whl
avp --help
```

Use these artifact URLs for the beta. They are distributed through GitHub,
not the package registries. Starting with 0.8.0, `avp update` reads the release
manifest and installs its SDK along with the CLI. To upgrade an older CLI to
0.8.0, use the installation command above with `--force`.

## Publish

Set each package's version and update its lockfile. Python projects have their
own uv lockfiles; TypeScript packages share the root npm workspace lockfile.
Before an SDK release, run `make sdk-data` and commit the refreshed snapshots.
Run `make check`, commit, and push the branch.

From the clean, pushed branch, publish the SDKs first:

```sh
make release-sdk-python
make release-sdk-typescript
```

Wait for both SDK releases, then publish the affected adapters:

```sh
make release-agent NAME=pi
```

`NAME` is a built-in name from `avp agent list --builtin`. The GitHub Packages
workflow builds and installs each artifact outside the checkout with its
released SDK, then checks the adapter's `ping` and `describe` commands.

After the adapters are released, publish and pin their images, then release
the CLI:

```sh
make agent-images
make release-cli
```

Each release target creates and pushes an annotated tag using the package
version. Existing tags are never overwritten. Bump the version for another
release. Tags are `sdk-python-v<version>`, `sdk-typescript-v<version>`,
`agent-<name>-v<version>`, and `cli-v<version>`.

### Built-in agent images

The CLI installs images at `ghcr.io/portofcontext/<agent_name>:<version>`, pinned
by digest in `avp-cli/src/avp_cli/agents/builtins.json`.

1. Update the agent version in the catalog and its Dockerfile. The Dockerfile
   installs the released adapter and SDK artifacts and needs no source context.
2. Push the branch and run the Agent images workflow on it. It checks `ping`
   before publishing amd64 and arm64 images. Published versions are left intact.
3. Make a new image package public in the organization's package settings.
4. Run `make agent-images`, commit the image digests, and push before releasing
   the CLI.

Without an image pin, or with `--build`, the CLI builds the packaged Dockerfile
in an empty context. It installs the same released packages.

To build and install-check an artifact locally, use an empty output directory:

```sh
python scripts/release.py build sdk-python --out /tmp/avp-sdk-release
```

The command accepts every package named by the release targets. Dependent
packages require their SDK release to exist first.

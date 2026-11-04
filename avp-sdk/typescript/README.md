# AVP TypeScript SDK

The TypeScript SDK for the [AVP v0.1 specs](../../spec/v0.1/). Its scope and
behavior are defined in the [SDK guide](../README.md), with Python as the reference.

The npm package is `@agent-voyager-project/sdk`. It uses ES modules and requires
Node 22.12 or newer. Import wire types and parsers from the `commission`,
`descriptor`, and `trajectory` subpaths. `parseTrajectoryEvent` skips unknown
event types when reading a Trajectory.

The agent CLI passes its run callback an `AbortSignal` for SIGINT and SIGTERM.
The callback ends its Trajectory and rethrows the abort; the CLI exits with 130.

## Install

```sh
npm install https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-typescript-v0.1.0-beta.1/agent-voyager-project-sdk-0.1.0-beta.1.tgz
```

## Development

From the repository root:

```sh
make sdk-typescript-check
make sdk-typescript-generate
make sdk-data-check
```

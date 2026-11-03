# AVP Rust SDK

The Rust SDK for the [AVP v0.1 specs](../../spec/v0.1/). Its scope and behavior
are defined in the [SDK guide](../README.md), with Python as the reference.

The crate is `avp`. Wire types are generated from the schemas; deserialize
with Serde. Use `trajectory::parse_trajectory_event` to skip unknown event
types when reading a Trajectory.

The SDK is synchronous. The agent CLI passes its run callback a SIGINT/SIGTERM
interruption flag. The callback ends its Trajectory and returns; the CLI exits
with 130.

## Development

From the repository root:

```sh
make sdk-rust-check
make sdk-rust-generate
make sdk-data
```

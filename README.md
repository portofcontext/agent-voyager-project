<div align="center">
  <img src="assets/logo.svg" alt="AVP Logo" height="202">
  <h1>Agent Voyager Project (AVP)</h1>
</div>

AI agents are hard to evaluate and hard to move between platforms. Every framework emits different telemetry, so every observer writes its own adapter. AVP standardizes the wire: a uniform event stream (model calls, tool uses, costs, outcomes) that any agent can emit and any platform can read.

> **(v0.1):** AVP Trajectory · AVP Agent Descriptor

> **(v0.1-beta):** AVP Commission · AVP Resolver API

We're rolling it out in two stages.

**Stage 1: standardize the journey.** Stable at v0.1. The [Trajectory Spec](spec/trajectory/v0.1/trajectory.md) defines the event stream every agent emits as it runs. The [Agent Descriptor Spec](spec/agent-descriptor/v0.1/agent-descriptor.md) defines what an agent advertises about itself. Together they make any agent observable the same way, regardless of which SDK or model it runs on.

**Stage 2: standardize how we pack the ships.** Beta at v0.1-beta. The [Commission Spec](spec/commission/v0.1-beta/commission.md) defines the run-config a supervisor hands an agent at startup. The [Resolver API](spec/resolver/v0.1-beta/resolver.md) defines the JSON-RPC channel the agent uses to dereference Commission refs at runtime. Together they describe a portable protocol for supervisor-driven runs: secrets and MCP connection material stay in the supervisor's resolver service, the agent dereferences refs at startup, and every round-trip is recorded on the trajectory.

AVP does not invent new wire formats when good ones already exist. It reuses [CloudEvents](https://cloudevents.io/) for event envelopes, [OpenTelemetry](https://opentelemetry.io/) for spans and token usage, [JSON-RPC](https://www.jsonrpc.org/specification) for the resolver, [MCP](https://modelcontextprotocol.io/) for tool dispatch, and [Agent Skills](https://agentskills.io/specification) for skill files. The work AVP does on top is small and focused. See [FOUNDATIONS.md](FOUNDATIONS.md) for the full mapping and where related work (such as Harbor's ATIF format) fits.

AVP is built and maintained by the [Port of Context](https://github.com/portofcontext) team and is licensed under MIT.

---

## To start using AVP

quickstart

For a complete walk through that builds a Commission, runs an agent, and prints the trajectory, see [`python/supervisors/simple-supervisor-example/`](python/supervisors/simple-supervisor-example/). The example suite is the fastest way to see AVP end to end.

## Proposals

 See [`proposals/`](proposals/) for the AVP-RFC process if you want to propose a change to the spec.

## Where to learn more

- [FOUNDATIONS.md](FOUNDATIONS.md) covers the upstream specs AVP builds on and what AVP adds on top.
- [PATTERNS.md](PATTERNS.md) is the integration guide: the shapes an application can take to wire onto AVP, with composition sketches and links to worked examples.
- [`spec/v0.1/`](spec/v0.1/) is the normative specification, organized by spec.
- [`conformance/v0.1/`](conformance/v0.1/) is the language agnostic test suite every conforming implementation MUST pass.
- [SKILL.md](SKILL.md) is a skill file for AI assistants working inside this repo.

<div align="center">
  <img src="assets/avp-icon.png" height="48" alt="AVP ship icon">
</div>


## Support

If something does not work, please open an [issue](https://github.com/portofcontext/agent-voyager-project/issues). For questions, use the [GitHub Discussions board](https://github.com/portofcontext/agent-voyager-project/discussions).

<div align="center">
  <sub>Built by the <a href="https://github.com/portofcontext">Port of Context</a> team</sub>
</div>

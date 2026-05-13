<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main/assets/avp-white.png">
    <img src="https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main/assets/avp.png" alt="AVP Logo" style="height: 128px">
  </picture>
  <h1>Agent Voyager Project (AVP)</h1>
</div>

> **(Stable, v0.1):** AVP Trajectory · AVP Agent Descriptor
> **(Beta, v0.1-beta):** AVP Commission · AVP Resolver API

Build an AI agent today and the framework decides what its trajectory looks like: Anthropic emits one shape of telemetry, OpenAI another, your custom loop a third. Audit pipelines and orchestration platforms that watch agents end up writing one adapter per framework.

AVP is an open standard for the wire those tools read. Agents that speak it emit a uniform event stream (model calls, tool uses, costs, errors), so an observer reads the same shape across every agent. AVP also defines how supervisors trigger and provision agents, keeping secrets and connection material off the wire.

We're rolling it out in two stages.

**Stage 1: standardize the journey.** Stable at v0.1. The [Trajectory Spec](spec/trajectory/v0.1/trajectory.md) defines the event stream every agent emits as it runs. The [Agent Descriptor Spec](spec/agent-descriptor/v0.1/agent-descriptor.md) defines what an agent advertises about itself. Together they make any agent observable the same way, regardless of which SDK or model it runs on.

**Stage 2: standardize how we pack the ships.** Beta at v0.1-beta. The [Commission Spec](spec/commission/v0.1-beta/commission.md) defines the run-config a supervisor hands an agent at startup. The [Resolver API](spec/resolver/v0.1-beta/resolver.md) defines the JSON-RPC channel the agent uses to dereference Commission refs at runtime. Together they describe a portable protocol for supervisor-driven runs: secrets and MCP connection material stay in the supervisor's resolver service, the agent dereferences refs at startup, and every round-trip is recorded on the trajectory.

### todo image from website

AVP does not invent new wire formats when good ones already exist. It reuses [CloudEvents](https://cloudevents.io/) for event envelopes, [OpenTelemetry](https://opentelemetry.io/) for spans and token usage, [JSON-RPC](https://www.jsonrpc.org/specification) for the resolver, [MCP](https://modelcontextprotocol.io/) for tool dispatch, and [Agent Skills](https://agentskills.io/specification) for skill files. The work AVP does on top is small and focused. See [FOUNDATIONS.md](FOUNDATIONS.md) for the full mapping and where related work (such as Harbor's ATIF format) fits.

AVP is built and maintained by the [Port of Context](https://github.com/portofcontext).

---

## The four specs

| Spec | Stage | Status | What it covers |
|---|---|---|---|
| [**AVP Trajectory**](spec/trajectory/v0.1/trajectory.md) | Agent journey | **Stable v0.1** | The stream of events an agent emits as it runs: lifecycle, model turns, tool calls, costs, errors. |
| [**AVP Agent Descriptor**](spec/agent-descriptor/v0.1/agent-descriptor.md) | Agent journey | **Stable v0.1** | What an agent advertises about itself before a run begins: identity, supported models, built-in tools / skills / subagents. |
| [**AVP Commission**](spec/commission/v0.1-beta/commission.md) | Packing the ships | **Beta v0.1-beta** | The run-config a supervisor sends to an agent at startup. Refs only, no inline material, no secrets. |
| [**AVP Resolver API**](spec/resolver/v0.1-beta/resolver.md) | Packing the ships | **Beta v0.1-beta** | The JSON-RPC protocol an agent calls to dereference Commission refs at runtime. |

## To start using AVP

quickstart here

- Python: [`python/avp/`](python/avp/)
- Rust: [`rust/avp/`](rust/avp/)
- TypeScript: [`typescript/avp/`](typescript/avp/)


## Proposals
See [`proposals/`](proposals/) for the AVP-RFC process if you want to propose a change to a spec. Stage 1 specs require backward-compatible changes within v1 and a deprecation period for removals; Stage 2 specs can take breaking changes within v0.

## Where to learn more

- [FOUNDATIONS.md](FOUNDATIONS.md): the specs each stage builds on (CloudEvents and OTel for the agent journey; JSON-RPC, MCP, and Agent Skills for packing the ships).
- [PATTERNS.md](PATTERNS.md): integration patterns.
- [`spec/`](spec/): the normative specifications.
- [`conformance/`](conformance/): the language-agnostic test suite every conforming implementation MUST pass.

## Support

If something does not work, please open an [issue](https://github.com/portofcontext/agent-voyager-project/issues). For questions, use the [GitHub Discussions board](https://github.com/portofcontext/agent-voyager-project/discussions).

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main/assets/avp-white.png">
    <img src="https://raw.githubusercontent.com/portofcontext/agent-voyager-project/main/assets/avp.png" alt="AVP Logo" style="height: 128px">
  </picture>
  <h1>Agent Voyager Project (AVP)</h1>
</div>

> **Status:** Draft v0.1

AVP is an open standard for AI agents and the systems that run them. The supervisor sends a job, the agent runs it, and the agent reports back. Both sides know what to expect because both sides speak AVP.

<div align="center">
<pre>
≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈

   I.   SUPERVISOR  ═════ Commission ══════▶  AGENT
        what to do · which model · what's available

  II.   AGENT  ◀═══ avp.resolve(ref) ═══▶  SUPERVISOR
        MCP connections · skill content · subagent commissions

 III.   AGENT  ═════ Trajectory ══════▶  SUPERVISOR
        every model + tool call · usage · outcome

≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈≈
</pre>
</div>

A typical run looks like this. A supervisor (the system) sends a small JSON document called a **Commission** to an agent. The Commission says what to do, which model to use, and what outside resources are available. The agent runs the work and sends back a **trajectory**, which is a stream of events that records every model call, every tool use, what the run cost, and how it ended. Both sides know exactly what to expect because both sides speak AVP.

AVP picks a shared vocabulary so any agent can plug into any platform that speaks it. It does not invent new wire formats when good ones already exist. AVP reuses [CloudEvents](https://cloudevents.io/) for the event envelope, [OpenTelemetry](https://opentelemetry.io/) for spans and token usage, [JSON-RPC](https://www.jsonrpc.org/specification) for the resource lookup service, [MCP](https://modelcontextprotocol.io/) for tools, and [Agent Skills](https://agentskills.io/specification) for skill files. The work AVP does on top is small and focused. Read [FOUNDATIONS.md](FOUNDATIONS.md) for the full mapping and where related work (such as Harbor's ATIF format) fits.

AVP is built and maintained by the [Port of Context](https://github.com/portofcontext) team and is licensed under MIT.

---

## To start using AVP

If you want to run an AI agent that emits AVP events out of the box, install the reference agent built on the Claude Agent SDK:

- [`avp-claude-agent`](python/agents/avp-claude-agent/) wraps the Claude Agent SDK, which ships its own loop and tools.

If you want to build your own agent on top of the raw Anthropic Messages API, install the SDK adapter and copy the reference agent from the examples:

- [`avp-anthropic`](python/sdks/avp-anthropic/) is the SDK adapter: a `ModelDriver`, a `TracedClient`, and Commission-to-API translators. The Anthropic API ships no loop or tools, so this package doesn't either; agents wrap it.
- The reference agent at [`python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py`](python/supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py) wires `avp-anthropic` to `AVPAgent` plus a local `ShellTools`. Examples 01 and 05 spawn it.

If you want to consume an AVP trajectory from another language, install the typed bindings. They are generated from the same JSON Schemas the Python types come from, so they cannot drift:

- Python: [`python/avp/`](python/avp/)
- Rust: [`rust/avp/`](rust/avp/)
- TypeScript: [`typescript/avp/`](typescript/avp/)

For a complete walk through that builds a Commission, runs an agent, and prints the trajectory, see [`python/supervisors/simple-supervisor-example/`](python/supervisors/simple-supervisor-example/). The example suite is the fastest way to see AVP end to end.

## To start developing AVP

The repo is a multi-language workspace. The Python side uses [uv](https://github.com/astral-sh/uv) with its workspace root at [`python/`](python/); Rust and TypeScript packages each have their own `Cargo.toml` / `package.json`. Run everything from the repo root:

```bash
git clone https://github.com/portofcontext/agent-voyager-project
cd agent-voyager-project
make sync           # `uv --directory python sync` under the hood
make check
```

`make help` lists every target. `make check` runs the free checks (format, lint, tests, conformance, bindings drift detection). `make smoke` runs the full matrix against real Anthropic models and costs about $0.10 to $0.20 per run.

See [CLAUDE.md](CLAUDE.md) for the contributor checklist. See [`proposals/`](proposals/) for the AVP-RFC process if you want to propose a change to the spec.

## What AVP defines

AVP is split into four specs. Each one can be adopted on its own. Most consumers use them together, but the choice is yours.

| Sub-spec | What it covers |
|---|---|
| [AVP Trajectory](spec/v0.1/trajectory.md) | The stream of events an agent emits as it runs. |
| [AVP Commission](spec/v0.1/commission.md) | The run configuration the supervisor sends to the agent at startup. |
| [AVP Agent Descriptor](spec/v0.1/agent-descriptor.md) | What an agent advertises about itself before a run begins. |
| [AVP Resolver API](spec/v0.1/resolver.md) | The JSON-RPC service the agent calls to look up the resources the Commission referenced. |

Three of these are data-shape specs. They describe a JSON document and nothing more. The Resolver API is the only one that defines a two party wire protocol. The umbrella [`spec/v0.1/README.md`](spec/v0.1/README.md) indexes all four and the shared concerns (transport, versioning, deployment scope).

## Where to learn more

- [FOUNDATIONS.md](FOUNDATIONS.md) covers the upstream specs AVP builds on and what AVP adds on top.
- [`spec/v0.1/`](spec/v0.1/) is the normative specification, organized by spec.
- [`conformance/v0.1/`](conformance/v0.1/) is the language agnostic test suite every conforming implementation MUST pass.
- [SKILL.md](SKILL.md) is a skill file for AI assistants working inside this repo.

## Support

If something does not work, please open an [issue](https://github.com/portofcontext/agent-voyager-project/issues). For questions, use the [GitHub Discussions board](https://github.com/portofcontext/agent-voyager-project/discussions).

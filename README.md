<div align="center">
  <img src="assets/logo.svg" alt="AVP Logo" height="202">
  <h1>Agent Voyager Project (AVP)</h1>
</div>

> **Status:** Draft v0.1

AVP is an open standard for AI agents and the systems that run them. A supervisor sends a job, the agent runs it and reports back, and both sides know what to expect because both sides speak AVP.

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

The supervisor sends a small JSON **Commission** (what to do, which model, what resources are available); the agent runs the work and streams back a **Trajectory** of events that records every model and tool call, what the run cost, and how it ended.

AVP picks a shared vocabulary instead of inventing new wire formats: [CloudEvents](https://cloudevents.io/) for the event envelope, [OpenTelemetry](https://opentelemetry.io/) for spans and token usage, [JSON-RPC](https://www.jsonrpc.org/specification) for resource lookup, [MCP](https://modelcontextprotocol.io/) for tools, and [Agent Skills](https://agentskills.io/specification) for skill files. What AVP adds on top is small. See [FOUNDATIONS.md](FOUNDATIONS.md) for the full mapping.

Built and maintained by the [Port of Context](https://github.com/portofcontext) team.

---

## Use AVP

- **Run an agent that emits AVP out of the box:** [`avp-claude-agent-sdk`](agents/avp-claude-agent-sdk/python/) wraps the Claude Agent SDK, which ships its own loop and tools.
- **Build your own agent on the raw Anthropic Messages API:** [`avp-anthropic`](sdks/avp-anthropic/) is the SDK adapter: a per-turn translator (`AnthropicModelDriver`), a drop-in traced client, and Commission-to-API translators. The API ships no loop or tools, so neither does the adapter. The reference agent at [`_anthropic_reference_agent.py`](supervisors/simple-supervisor-example/examples/_anthropic_reference_agent.py) inlines its own loop over the adapter with a local `ShellTools`; example 01 spawns it as a subprocess.
- **Consume a trajectory from another language:** typed bindings generated from the same JSON Schemas the Python types use, so they cannot drift: [Python](avp/bindings/python/), [Rust](avp/bindings/rust/), [TypeScript](avp/bindings/typescript/).

For an end-to-end walkthrough that builds a Commission, runs an agent, and prints the trajectory, see [`supervisors/simple-supervisor-example/`](supervisors/simple-supervisor-example/).

## Develop AVP

The core project lives under [`avp/`](avp/) (spec plus Python/Rust/TS bindings), with [`agents/`](agents/), [`sdks/`](sdks/), and [`supervisors/`](supervisors/) alongside. Python uses [uv](https://github.com/astral-sh/uv) with its workspace root at the repo root.

```bash
git clone https://github.com/portofcontext/agent-voyager-project
cd agent-voyager-project
make sync && make check
```

`make help` lists every target. `make check` is the free floor (format, lint, tests, conformance, bindings drift). `make smoke` runs the full matrix against real Anthropic models and costs about $0.10 to $0.20 per run. See [CLAUDE.md](CLAUDE.md) to contribute and [`proposals/`](proposals/) for the spec RFC process.

## What AVP defines

Four specs, each adoptable on its own:

| Sub-spec | What it covers |
|---|---|
| [Trajectory](avp/core/spec/v0.1/trajectory.md) | The stream of events an agent emits as it runs. |
| [Commission](avp/core/spec/v0.1/commission.md) | The run configuration the supervisor sends at startup. |
| [Agent Descriptor](avp/core/spec/v0.1/agent-descriptor.md) | What an agent advertises about itself before a run. |
| [Resolver API](avp/core/spec/v0.1/resolver.md) | The JSON-RPC service the agent calls to look up referenced resources. |

The first three are data-shape specs; the Resolver API is the only two-party wire protocol. The umbrella [`avp/core/spec/v0.1/README.md`](avp/core/spec/v0.1/README.md) indexes all four and the shared concerns.

## More

- [PATTERNS.md](PATTERNS.md): how an application wires onto AVP, with worked examples.
- [`avp/core/conformance/`](avp/core/conformance/src/avp_conformance/cases/v0.1/): the language-agnostic suite every conforming implementation MUST pass, driven by the `avp-conformance` CLI.
- [SKILL.md](SKILL.md): a skill file for AI assistants working in this repo.

Questions or bugs: open an [issue](https://github.com/portofcontext/agent-voyager-project/issues) or use [Discussions](https://github.com/portofcontext/agent-voyager-project/discussions).

# Wire a new agent to the AVP conformance suite

Start from `agents/_template/<lang>/` (its README explains each file).

- [ ] **Copy and rename** the template to `agents/<name>/<lang>/`: package,
      `AGENT_NAME`, and the command in `avp-conformance.json`.
- [ ] **Entrypoint**: keep the stock one (`avp.agent_cli.main` /
      `avp::agent_cli::main`) and supply `describe()` and `run(commission, sink)`.
      `ping` must not boot the agent.
- [ ] **Translate** native content to AVP blocks (tool calls as `tool_use`) and
      native usage to `Usage` (`input_tokens` includes cache reads and writes).
- [ ] **Report** through the `Recorder`: `prelude`, fail-fast checks, `start`,
      then `assistant` / `tool_result` / `subagent_*`, and `stop` on every path.
- [ ] **Honor the Commission**: model, prompts, `enabled_builtin_*` under your
      agent's key, inline `mcp_servers` and `skills`.
- [ ] **Seam test** a recorded or stubbed run through the entrypoint.
- [ ] **Free checks**: `avp-conformance ping --agent <manifest>` and
      `avp-conformance describe --agent <manifest>`.
- [ ] **Suite on a real model**: `avp-conformance check --agent <manifest>
      --suite v0.1` (one case: `--case <path>`; keep trajectories:
      `--dump-dir <dir>`).

Manifest model: `manifest.py`. Case and `--built-in` fixture models:
`case.py`. Recorder rules: `recorder/v0.1/README.md`.

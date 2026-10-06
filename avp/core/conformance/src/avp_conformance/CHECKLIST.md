# Wire a new agent to the AVP conformance suite

The walkthrough with the reasons: `agents/_template/README.md`.

- [ ] **Scaffold**: `make new-agent NAME=avp-<sdk>` (or `make new-agent-rust`),
      then run the `next:` commands it prints.
- [ ] **Harness**: replace the stand-in `harness` with the SDK; report its
      events through the `Recorder` (`assistant` with tool calls as `tool_use`,
      `tool_result`, `subagent_*`, `stop` on every path).
- [ ] **Translate** native content to AVP blocks and native usage to `Usage`
      (`input_tokens` includes cache reads and writes).
- [ ] **Commission**: model, provider, prompts, `output_schema`, inline
      `mcp_servers` and `skills`, `enabled_builtin_*` under your agent's key;
      pass the offered names to `preflight`.
- [ ] **Seam test** a recorded or stubbed run through the entrypoint.
- [ ] **Free checks**: `make test`, `make conformance`.
- [ ] **Suite on a real model**: `avp-conformance check --agent <manifest>
      --suite v0.1 --model <origin>/<model>` (SKIP = a surface you don't
      declare; one case: `--case <path>`; keep trajectories: `--dump-dir <dir>`).
- [ ] **Ship**: out of tree, a manifest `container` block; in tree,
      `AGENT_SOURCES` + release workflow + `make release-<name>` (template
      README §5).

Manifest model: `manifest.py`. Case model (incl. `requires`) and `--built-in`
fixture: `case.py`. Recorder rules: `recorder/v0.1/README.md`.

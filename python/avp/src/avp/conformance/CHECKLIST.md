# Wire a new SDK to the AVP conformance suite

Step-by-step. Worked reference: `python/agents/avp-claude-agent-sdk/` (look
at `src/avp_claude_agent_sdk/conformance.py` and `avp-conformance.json`).

## 1. Add a conformance entrypoint module to your SDK

- [ ] Create `<your_sdk_pkg>/conformance.py` (any name; manifest will point at it).
- [ ] Use stdlib `argparse` — keeps the SDK package free of CLI deps.
- [ ] Expose two subcommands: `ping` and `run`.
- [ ] Add a `main(argv=None)` entry function and a `if __name__ == "__main__": raise SystemExit(main())` shim.

## 2. Implement `ping --out <path.jsonl>`

- [ ] Write a single line `{"type": "pong"}` to `--out`.
- [ ] Exit `0`.
- [ ] No imports of the agent loop, no model calls — `ping` is a liveness check, not a smoke test.

## 3. Write the manifest

- [ ] Create `avp-conformance.json` at your SDK's repo root (or wherever — paths in the manifest are relative to its own location).
- [ ] Match the `AgentManifest` model (`python/avp/src/avp/conformance/manifest.py`):

```json
{
  "command": ["python", "-m", "your_sdk_pkg.conformance"],
  "cwd": ".",
  "env": {},
  "description": "your_sdk_pkg conformance entrypoint"
}
```

- [ ] `command` is the prefix — the conformance CLI appends `ping --out ...` or `run --commission ... --out ...`.
- [ ] `cwd` resolves relative to the manifest file's location, not the conformance CLI's CWD.

## 4. Verify ping works end-to-end

- [ ] From the workspace: `uv --directory python run avp-conformance ping --agent <path-to-your-manifest.json>`.
- [ ] Expect `PASS  ping` and exit `0`.
- [ ] If you get `FAIL  ping  exit=N`, read the stderr tail — usually a Python import path issue or a missing dep.

## 5. Implement `run --commission <json|path> [--built-in <json|path>] --out <path.jsonl>`

- [ ] Parse `--commission` accepting either an inline JSON string OR a path to a JSON file. Deserialize via `avp.commission.Commission`.
- [ ] Parse `--built-in` (optional) the same way. Deserialize via `avp.conformance.case.AgentBuiltins`.
- [ ] When `--built-in` is present, behave AS IF those are your SDK's built-ins for this run (system_prompt, tools, skills, mcp_servers, subagents), then apply Commission overrides per the AVP merge spec.
- [ ] When `--built-in` is absent, use your SDK's real built-ins.
- [ ] Run the agent loop. For every AVP trajectory event emitted, write one JSON object as a line to `--out`. Use the `avp.trajectory.*` Pydantic models to serialize.
- [ ] Exit `0` after `agent_stopped`. Non-zero is a crash; stderr is surfaced to the user by the conformance CLI.

## 6. Verify run works end-to-end (once cases are promoted)

- [ ] `uv --directory python run avp-conformance run --agent <manifest> --suite v0.1`.
- [ ] Until cases land in `python/avp/src/avp/conformance/cases/v0.1/`, drive a single case manually with `--case <path>`.

## Pointers

- Manifest model: `python/avp/src/avp/conformance/manifest.py`
- Case model + built-in fixture: `python/avp/src/avp/conformance/case.py`
- Commission, AgentDescriptor, Trajectory event types: `python/avp/src/avp/{commission,descriptor,trajectory}.py`
- Worked reference SDK entrypoint: `python/agents/avp-claude-agent-sdk/src/avp_claude_agent_sdk/conformance.py`
- Plan + decisions: `CONFORMANCE_PLAN.md` (repo root)

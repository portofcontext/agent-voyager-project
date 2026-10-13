/**
 * The stock entrypoint and the shared preflight checks.
 */
import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { dispatch, type AgentEntrypoint } from "../src/agent-cli.js";
import type { AgentDescriptor, Commission } from "../src/index.js";
import { preflight } from "../src/preflight.js";
import { Recorder } from "../src/recorder.js";

const DESCRIPTOR = { agent_name: "a", agent_version: "1.0", spec_version: "0.1" } as AgentDescriptor;

function commission(extra: Record<string, unknown> = {}): Commission {
  return { schema_version: "0.1", run_id: "r", model: "x/m", ...extra } as Commission;
}

test("preflight matches the Python and Rust checks", () => {
  const check = (extra: Record<string, unknown>) =>
    preflight(commission(extra), "a", "1.0", { tools: ["read"] })?.[0];
  assert.equal(check({}), undefined);
  assert.equal(check({ agent_versions: { a: "0.9" } }), "unsupported_agent_version");
  assert.equal(check({ enabled_builtin_subagents: { other: [] } }), "commission_collision");
  assert.equal(check({ enabled_builtin_tools: { a: ["read", "fly"] } }), "commission_collision");
  assert.equal(check({ enabled_builtin_tools: { a: [] } }), undefined);
  // An unchecked surface (no offered names) is not validated by name.
  assert.equal(check({ enabled_builtin_skills: { a: ["anything"] } }), undefined);
});

function agent(seen: { commission?: Commission; cwd?: string }): AgentEntrypoint {
  return {
    describe: () => DESCRIPTOR,
    run: async (c, sink) => {
      seen.commission = c;
      seen.cwd = process.cwd();
      const rec = new Recorder(sink, { runId: c.run_id });
      rec.prelude(c, DESCRIPTOR);
      rec.start();
      rec.stop("converged");
    },
  };
}

test("ping, describe, and run honor the file contract", async () => {
  const dir = mkdtempSync(join(tmpdir(), "avp-cli-"));
  const seen: { commission?: Commission; cwd?: string } = {};

  await dispatch(agent(seen), ["ping", "--out", join(dir, "pong")]);
  assert.deepEqual(JSON.parse(readFileSync(join(dir, "pong"), "utf8")), { type: "pong" });

  await dispatch(agent(seen), ["describe", `--out=${join(dir, "descriptor.json")}`]);
  assert.deepEqual(JSON.parse(readFileSync(join(dir, "descriptor.json"), "utf8")), DESCRIPTOR);

  writeFileSync(join(dir, "built-in.json"), JSON.stringify({ system_prompt: "fixture", prompt: "ignored" }));
  await dispatch(agent(seen), [
    "run",
    "--commission",
    JSON.stringify(commission({ prompt: "mine" })),
    "--built-in",
    join(dir, "built-in.json"),
    "--out",
    join(dir, "out.ndjson"),
  ]);
  assert.equal(seen.commission?.system_prompt, "fixture");
  assert.equal(seen.commission?.prompt, "mine");
  const types = readFileSync(join(dir, "out.ndjson"), "utf8")
    .trimEnd()
    .split("\n")
    .map((l) => JSON.parse(l).type);
  assert.deepEqual(types, [
    "avp.run_requested",
    "avp.agent_described",
    "avp.agent_started",
    "avp.agent_stopped",
  ]);
});

test("run enters AVP_WORKSPACE and restores the previous directory", async () => {
  const dir = mkdtempSync(join(tmpdir(), "avp-ws-"));
  const workspace = mkdtempSync(join(tmpdir(), "avp-ws-inner-"));
  const before = process.cwd();
  const seen: { cwd?: string } = {};
  process.env.AVP_WORKSPACE = workspace;
  try {
    await dispatch(agent(seen), ["run", "--commission", JSON.stringify(commission()), "--out", join(dir, "o")]);
  } finally {
    delete process.env.AVP_WORKSPACE;
  }
  assert.equal(seen.cwd, realpathSync(workspace));
  assert.equal(process.cwd(), before);
});

test("usage errors are distinguished from failures", async () => {
  await assert.rejects(dispatch(agent({}), []), /missing command/);
  await assert.rejects(dispatch(agent({}), ["run", "--out", "x"]), /run needs --commission/);
  await assert.rejects(dispatch(agent({}), ["fly"]), /unknown command/);
});

test("SIGTERM during run aborts its signal and reports interrupted", async () => {
  const dir = mkdtempSync(join(tmpdir(), "avp-sig-"));
  const slow: AgentEntrypoint = {
    describe: () => DESCRIPTOR,
    run: async (c, sink, signal) => {
      const rec = new Recorder(sink, { runId: c.run_id });
      rec.prelude(c, DESCRIPTOR);
      rec.start();
      await new Promise((resolve) => signal.addEventListener("abort", resolve, { once: true }));
      rec.stop("interrupted");
    },
  };
  const out = join(dir, "o");
  const pending = dispatch(slow, ["run", "--commission", JSON.stringify(commission()), "--out", out]);
  setTimeout(() => process.emit("SIGTERM"), 20);
  assert.equal(await pending, "interrupted");
  const last = JSON.parse(readFileSync(out, "utf8").trimEnd().split("\n").at(-1)!);
  assert.equal(last.data["avp.reason"], "interrupted");
  assert.equal(process.listenerCount("SIGTERM"), 0, "handlers are removed after the run");
});

test("the interrupt listener stays attached while the signal is delivered", async () => {
  // `signal-exit` (in Pi's dependency tree) re-raises a signal, killing the
  // process, when it finds no other listener at delivery time; a `once`
  // listener has already detached by then.
  const dir = mkdtempSync(join(tmpdir(), "avp-sigexit-"));
  const seen: number[] = [];
  const probe = () => seen.push(process.listenerCount("SIGTERM"));
  const agent: AgentEntrypoint = {
    describe: () => DESCRIPTOR,
    run: async (c, sink, signal) => {
      process.on("SIGTERM", probe);
      const rec = new Recorder(sink, { runId: c.run_id });
      rec.start();
      await new Promise((resolve) => signal.addEventListener("abort", resolve, { once: true }));
      rec.stop("interrupted");
      process.off("SIGTERM", probe);
    },
  };
  const pending = dispatch(agent, ["run", "--commission", JSON.stringify(commission()), "--out", join(dir, "o")]);
  setTimeout(() => process.emit("SIGTERM"), 20);
  assert.equal(await pending, "interrupted");
  assert.deepEqual(seen, [2], "the entrypoint's listener was still attached");
});

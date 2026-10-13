/**
 * Seam tests: Pi's real session loop, tools, and MCP extension on a scripted
 * (`faux`) model, through the adapter, into the Recorder's trajectory.
 */
import { strict as assert } from "node:assert";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { MemorySink, type Commission } from "@avp/types";
import {
  fauxAssistantMessage,
  fauxProvider,
  fauxText,
  fauxToolCall,
  type FauxResponseStep,
} from "@earendil-works/pi-ai";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

import { run } from "../src/agent.js";

type Json = Record<string, any>;

const MODEL = "claude-haiku-4-5";

const FIXTURE = (() => {
  let dir = dirname(fileURLToPath(import.meta.url));
  while (!existsSync(join(dir, "testing", "mcp", "avp_test_mcp.py"))) {
    if (dirname(dir) === dir) throw new Error("testing/mcp/avp_test_mcp.py not found");
    dir = dirname(dir);
  }
  return join(dir, "testing", "mcp", "avp_test_mcp.py");
})();

function commission(extra: Partial<Commission> = {}): Commission {
  return {
    schema_version: "0.1",
    run_id: "pi-seam",
    model: `anthropic/${MODEL}`,
    prompt: "do the thing",
    ...extra,
  } as Commission;
}

/** Run the adapter in a fresh workspace on a scripted Anthropic-shaped model. */
async function runScripted(
  c: Commission,
  responses: FauxResponseStep[],
  opts: { signal?: AbortSignal; tokensPerSecond?: number } = {},
): Promise<{ events: Json[]; cwd: string }> {
  const home = mkdtempSync(join(tmpdir(), "avp-pi-home-"));
  const cwd = mkdtempSync(join(tmpdir(), "avp-pi-ws-"));
  const faux = fauxProvider({
    provider: "anthropic",
    models: [{ id: MODEL }],
    ...(opts.tokensPerSecond ? { tokensPerSecond: opts.tokensPerSecond } : {}),
  });
  faux.setResponses(responses);
  const modelRuntime = await ModelRuntime.create({
    authPath: join(home, "auth.json"),
    modelsPath: null,
    refreshOnCreate: false,
  });
  modelRuntime.registerNativeProvider(faux.provider);
  await modelRuntime.setRuntimeApiKey("anthropic", "test-key");
  const sink = new MemorySink();
  const previous = process.cwd();
  process.chdir(cwd);
  try {
    await run(c, sink, { agentDir: home, modelRuntime, signal: opts.signal });
  } finally {
    process.chdir(previous);
  }
  return { events: JSON.parse(JSON.stringify(sink.events)), cwd };
}

const types = (events: Json[]) => events.map((e) => e.type.replace(/^avp\./, ""));
const one = (events: Json[], type: string) => events.find((e) => e.type === `avp.${type}`)!;

test("a built-in tool round trip is one turn per inference with paired tool events", async () => {
  const { events, cwd } = await runScripted(commission(), [
    fauxAssistantMessage([fauxToolCall("write", { path: "out.txt", content: "OK" }, { id: "call_w" })], {
      stopReason: "toolUse",
    }),
    fauxAssistantMessage([fauxText("DONE")]),
  ]);
  assert.deepEqual(types(events), [
    "run_requested",
    "agent_described",
    "agent_started",
    "assistant_message",
    "tool_invoked",
    "tool_returned",
    "assistant_message",
    "agent_stopped",
  ]);
  assert.equal(readFileSync(join(cwd, "out.txt"), "utf8"), "OK");

  const started = one(events, "agent_started").data;
  assert.deepEqual(
    started["avp.tools"].map((t: Json) => t.name),
    ["read", "bash", "edit", "write"],
  );
  const invoked = one(events, "tool_invoked").data;
  assert.equal(invoked["avp.tool.name"], "write");
  assert.equal(invoked["avp.tool.dispatch_target"], "local");
  const returned = one(events, "tool_returned").data;
  assert.equal(returned["avp.tool.call_id"], "call_w");
  assert.equal(returned["avp.tool_result"].is_error, false);

  const [first, second] = events.filter((e) => e.type === "avp.assistant_message").map((e) => e.data);
  assert.deepEqual(first["avp.content"][0], {
    type: "tool_use",
    id: "call_w",
    name: "write",
    input: { path: "out.txt", content: "OK" },
  });
  assert.deepEqual(first["avp.response.finish_reasons"], ["toolUse"]);
  for (const turn of [first, second]) {
    const u = turn["avp.usage"];
    // AVP input includes the cache split that Pi reports separately.
    assert.ok(u.input_tokens >= u.cache_read_input_tokens + u.cache_creation_input_tokens);
    assert.ok(u.output_tokens > 0);
    assert.equal(turn["avp.cost.source"], "computed");
    assert.equal(turn["avp.response.model"], MODEL);
  }
  const stopped = one(events, "agent_stopped").data;
  assert.equal(stopped["avp.reason"], "converged");
  assert.equal(stopped["avp.output"], "DONE");
});

test("Commission MCP tools run through Pi's MCP extension", async () => {
  const { events } = await runScripted(
    commission({
      mcp_servers: [{ type: "stdio", id: "avptest", command: ["python3", FIXTURE] }],
      enabled_builtin_tools: { "avp-pi": [] },
    }),
    [
      fauxAssistantMessage([fauxToolCall("mcp__avptest__Avptest_Echo", { text: "AVP-MCP" }, { id: "call_m" })], {
        stopReason: "toolUse",
      }),
      fauxAssistantMessage([fauxText("AVP-MCP")]),
    ],
  );
  const started = one(events, "agent_started").data;
  assert.deepEqual(started["avp.mcp_servers"], [{ id: "avptest", status: "connected" }]);
  const echo = started["avp.tools"].find((t: Json) => t.name === "mcp__avptest__Avptest_Echo");
  assert.equal(echo["avp.mcp_server_id"], "avptest");
  assert.ok(!started["avp.tools"].some((t: Json) => t.name === "write"), "empty allow-list hides built-ins");

  const invoked = one(events, "tool_invoked").data;
  assert.equal(invoked["avp.tool.dispatch_target"], "mcp_server");
  const result = one(events, "tool_returned").data["avp.tool_result"];
  assert.equal(result.is_error, false);
  assert.match(JSON.stringify(result.content), /AVP-MCP/);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("an MCP server that fails to connect is reported and left out", async () => {
  const { events } = await runScripted(
    commission({ mcp_servers: [{ type: "stdio", id: "broken", command: ["/nonexistent/avp-mcp"] }] }),
    [fauxAssistantMessage([fauxText("fine")])],
  );
  assert.deepEqual(types(events).slice(0, 4), ["run_requested", "agent_described", "error_occurred", "agent_started"]);
  assert.equal(one(events, "error_occurred").data["avp.error.code"], "mcp_connect_failed");
  assert.deepEqual(one(events, "agent_started").data["avp.mcp_servers"], [{ id: "broken", status: "failed" }]);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("a provider failure ends the run with a classified error", async () => {
  const { events } = await runScripted(commission(), [
    fauxAssistantMessage([], { stopReason: "error", errorMessage: "401 invalid x-api-key" }),
  ]);
  const error = one(events, "error_occurred").data;
  assert.equal(error["avp.error.code"], "auth_error");
  assert.match(error["avp.error.message"], /invalid x-api-key/);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "error");
  assert.ok(!types(events).includes("assistant_message"), "an empty failed inference is not a turn");
});

test("a Commission the agent cannot honor fails fast before agent_started", async () => {
  for (const [c, code] of [
    [commission({ enabled_builtin_tools: { "avp-pi": ["fly"] } }), "commission_collision"],
    [commission({ agent_versions: { "avp-pi": "9.9.9" } }), "unsupported_agent_version"],
    [commission({ model: "anthropic/no-such-model" }), "unsupported_model"],
    [commission({ provider: { id: "openrouter" } }), "unsupported_provider"],
  ] as const) {
    const { events } = await runScripted(c, []);
    assert.deepEqual(types(events), ["run_requested", "agent_described", "error_occurred", "agent_stopped"]);
    assert.equal(one(events, "error_occurred").data["avp.error.code"], code);
    assert.equal(one(events, "agent_stopped").data["avp.reason"], "error");
  }
});

test("an abort mid-inference stops the run as interrupted", async () => {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 300);
  const { events } = await runScripted(
    commission(),
    [fauxAssistantMessage([fauxText("word ".repeat(400))])],
    { signal: controller.signal, tokensPerSecond: 20 },
  );
  const last = events.at(-1)!;
  assert.equal(last.type, "avp.agent_stopped");
  assert.equal(last.data["avp.reason"], "interrupted");
  assert.ok(types(events).includes("agent_started"));
});

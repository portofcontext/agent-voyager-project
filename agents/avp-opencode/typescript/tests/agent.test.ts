/**
 * Seam tests: the real OpenCode server (the pinned binary), its loop, tools,
 * MCP client, and task subagents, on a scripted OpenAI Responses endpoint,
 * through the adapter, into the Recorder's trajectory. No network.
 */
import { strict as assert } from "node:assert";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

import { MemorySink, type Commission } from "@avp/types";

import { describe, run } from "../src/agent.js";
import { BUILTIN_SKILLS, BUILTIN_SUBAGENTS } from "../src/commission.js";
import { opencodeBinary } from "../src/server.js";
import { ScriptedModel, USAGE, type Step } from "./scripted.js";

type Json = Record<string, any>;

const MODEL = "gpt-4.1";

const FIXTURE = (() => {
  let dir = dirname(fileURLToPath(import.meta.url));
  while (!existsSync(join(dir, "testing", "mcp", "avp_test_mcp.py"))) {
    if (dirname(dir) === dir) throw new Error("testing/mcp/avp_test_mcp.py not found");
    dir = dirname(dir);
  }
  return join(dir, "testing", "mcp", "avp_test_mcp.py");
})();

let model: ScriptedModel;
before(async () => (model = await ScriptedModel.start()));
after(async () => model.close());

function commission(extra: Partial<Commission> = {}): Commission {
  return {
    schema_version: "0.1",
    run_id: "opencode-seam",
    model: `openai/${MODEL}`,
    provider: { id: "openai", base_url: model.baseUrl },
    prompt: "do the thing",
    ...extra,
  } as Commission;
}

/** Run the adapter in a fresh workspace against the scripted model. */
async function runScripted(
  c: Commission,
  steps: Step[] | ((cwd: string) => Step[]),
  opts: { signal?: AbortSignal } = {},
): Promise<{ events: Json[]; cwd: string }> {
  const cwd = mkdtempSync(join(tmpdir(), "avp-opencode-ws-"));
  model.script(typeof steps === "function" ? steps(cwd) : steps);
  const sink = new MemorySink();
  const previous = process.cwd();
  process.chdir(cwd);
  try {
    await run(c, sink, { env: { OPENAI_API_KEY: "test-key" }, signal: opts.signal });
  } finally {
    process.chdir(previous);
  }
  return { events: JSON.parse(JSON.stringify(sink.events)), cwd };
}

const types = (events: Json[]) => events.map((e) => e.type.replace(/^avp\./, ""));
const one = (events: Json[], type: string) => events.find((e) => e.type === `avp.${type}`)!;
const all = (events: Json[], type: string) => events.filter((e) => e.type === `avp.${type}`).map((e) => e.data);

test("the descriptor declares OpenCode's default tools, subagents, and skills", async () => {
  const d = await describe();
  assert.deepEqual(
    d.tools!.map((t) => t.name),
    ["bash", "read", "glob", "grep", "edit", "write", "task", "webfetch", "todowrite", "skill", "apply_patch"],
  );
  assert.ok(d.tools!.every((t) => t.description && t.inputSchema));
  assert.deepEqual(d.subagents!.map((s) => s.name).sort(), [...BUILTIN_SUBAGENTS].sort());
  assert.deepEqual(d.skills!.map((s) => s.name), [...BUILTIN_SKILLS]);
});

test("a built-in tool round trip is one turn per model response with paired tool events", async () => {
  // The write tool takes an absolute path; point it into the run's workspace.
  const { events, cwd: ws } = await runScripted(commission(), (cwd) => [
    { call: { id: "call_w", name: "write", args: { filePath: join(cwd, "out.txt"), content: "OK" } } },
    { text: "DONE" },
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
  assert.equal(readFileSync(join(ws, "out.txt"), "utf8"), "OK");

  const started = one(events, "agent_started").data;
  const names = started["avp.tools"].map((t: Json) => t.name);
  assert.ok(names.includes("write") && names.includes("edit") && !names.includes("apply_patch"));
  assert.deepEqual(started["avp.subagents"].map((s: Json) => s.name).sort(), ["explore", "general"]);
  const invoked = one(events, "tool_invoked").data;
  assert.equal(invoked["avp.tool.name"], "write");
  assert.equal(invoked["avp.tool.dispatch_target"], "local");
  const returned = one(events, "tool_returned").data;
  assert.equal(returned["avp.tool.call_id"], "call_w");
  assert.equal(returned["avp.tool_result"].is_error, false);

  const [first, second] = all(events, "assistant_message");
  assert.deepEqual(first["avp.content"], [
    { type: "tool_use", id: "call_w", name: "write", input: { filePath: join(ws, "out.txt"), content: "OK" } },
  ]);
  assert.deepEqual(first["avp.response.finish_reasons"], ["tool-calls"]);
  for (const turn of [first, second]) {
    // OpenCode reports input without the cache split; AVP input includes it.
    assert.deepEqual(turn["avp.usage"], {
      input_tokens: USAGE.input,
      output_tokens: USAGE.output,
      cache_read_input_tokens: USAGE.cached,
      cache_creation_input_tokens: 0,
    });
    assert.equal(turn["avp.cost.source"], "computed");
    assert.equal(turn["avp.response.model"], MODEL);
  }
  const stopped = one(events, "agent_stopped").data;
  assert.equal(stopped["avp.reason"], "converged");
  assert.equal(stopped["avp.output"], "DONE");
  // The run's system prompt rides on the request; the prompt is the user message.
  assert.match(JSON.stringify(model.requests[0]!.input), /do the thing/);
});

test("withholding edit leaves write and apply_patch callable, and the reverse", async () => {
  const offered = () => model.requests.at(-2)!.tools.map((t: Json) => t.name);
  const keepWrite = commission({ enabled_builtin_tools: { "avp-opencode": ["read", "write"] } });
  const { events, cwd: ws } = await runScripted(keepWrite, (cwd) => [
    { call: { id: "call_w", name: "write", args: { filePath: join(cwd, "out.txt"), content: "OK" } } },
    { text: "DONE" },
  ]);
  assert.deepEqual(offered().sort(), ["read", "write"]);
  assert.deepEqual(
    one(events, "agent_started").data["avp.tools"].map((t: Json) => t.name),
    ["read", "write"],
  );
  assert.equal(one(events, "tool_returned").data["avp.tool_result"].is_error, false);
  assert.equal(readFileSync(join(ws, "out.txt"), "utf8"), "OK");

  const keepEdit = commission({ enabled_builtin_tools: { "avp-opencode": ["read", "edit"] } });
  const edited = await runScripted(keepEdit, (cwd) => {
    writeFileSync(join(cwd, "in.txt"), "old");
    return [
      { call: { id: "call_e", name: "edit", args: { filePath: join(cwd, "in.txt"), oldString: "old", newString: "new" } } },
      { text: "DONE" },
    ];
  });
  assert.deepEqual(offered().sort(), ["edit", "read"]);
  assert.equal(one(edited.events, "tool_returned").data["avp.tool_result"].is_error, false);
  assert.equal(readFileSync(join(edited.cwd, "in.txt"), "utf8"), "new");
});

test("Commission MCP tools run through OpenCode's MCP client", async () => {
  const { events } = await runScripted(
    commission({
      mcp_servers: [{ type: "stdio", id: "avptest", command: ["python3", FIXTURE] }],
      enabled_builtin_tools: { "avp-opencode": [] },
      system_prompt: "You are terse.",
    }),
    [{ call: { id: "call_m", name: "avptest_Avptest_Echo", args: { text: "AVP-MCP" } } }, { text: "AVP-MCP" }],
  );
  const started = one(events, "agent_started").data;
  assert.deepEqual(started["avp.mcp_servers"], [{ id: "avptest", status: "connected" }]);
  const echo = started["avp.tools"].find((t: Json) => t.name === "mcp__avptest__Avptest_Echo");
  assert.equal(echo["avp.mcp_server_id"], "avptest");
  assert.ok(echo.inputSchema);
  assert.ok(!started["avp.tools"].some((t: Json) => !t["avp.mcp_server_id"]), "empty allow-list hides built-ins");

  // The model saw only the MCP tools, and the system prompt.
  const request = model.requests[0]!;
  assert.deepEqual(
    request.tools.map((t: Json) => t.name).filter((n: string) => !n.startsWith("avptest_")),
    [],
  );
  assert.match(JSON.stringify(request.instructions ?? request.input), /You are terse\./);

  const invoked = one(events, "tool_invoked").data;
  assert.equal(invoked["avp.tool.name"], "mcp__avptest__Avptest_Echo");
  assert.equal(invoked["avp.tool.dispatch_target"], "mcp_server");
  const result = one(events, "tool_returned").data["avp.tool_result"];
  assert.equal(result.is_error, false);
  assert.match(JSON.stringify(result.content), /AVP-MCP/);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("an MCP server that fails to connect is reported and the run continues", async () => {
  const { events } = await runScripted(
    commission({ mcp_servers: [{ type: "stdio", id: "broken", command: ["/nonexistent/avp-mcp"] }] }),
    [{ text: "fine" }],
  );
  assert.deepEqual(types(events).slice(0, 4), ["run_requested", "agent_described", "error_occurred", "agent_started"]);
  assert.equal(one(events, "error_occurred").data["avp.error.code"], "mcp_connect_failed");
  assert.deepEqual(one(events, "agent_started").data["avp.mcp_servers"], [{ id: "broken", status: "failed" }]);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("a provider failure ends the run with a classified error and no turn", async () => {
  for (const [status, body, code] of [
    [401, { error: { message: "Incorrect API key provided", type: "invalid_request_error", code: "invalid_api_key" } }, "auth_error"],
    // Google's shape: a 400 that names the key.
    [400, { error: { code: 400, message: "API key not valid. Please pass a valid API key.", status: "INVALID_ARGUMENT" } }, "auth_error"],
    [
      429,
      { error: { message: "You exceeded your current quota", type: "insufficient_quota", code: "insufficient_quota" } },
      "rate_limit",
    ],
  ] as const) {
    const startedAt = Date.now();
    const { events } = await runScripted(commission(), [{ status, body }, { status, body }, { status, body }]);
    const error = one(events, "error_occurred").data;
    assert.equal(error["avp.error.code"], code, JSON.stringify(error));
    assert.equal(one(events, "agent_stopped").data["avp.reason"], "error");
    assert.ok(!types(events).includes("assistant_message"), "a failed inference is not a turn");
    // Out of quota is not retried to exhaustion.
    assert.ok(Date.now() - startedAt < 20_000, `${code} took ${Date.now() - startedAt}ms`);
  }
});

test("a Commission the agent cannot honor fails fast before agent_started", async () => {
  for (const [c, code] of [
    [commission({ enabled_builtin_tools: { "avp-opencode": ["fly"] } }), "commission_collision"],
    [commission({ enabled_builtin_subagents: { other: [] } }), "commission_collision"],
    [commission({ agent_versions: { "avp-opencode": "9.9.9" } }), "unsupported_agent_version"],
    [commission({ model: "openai/no-such-model" }), "unsupported_model"],
    [commission({ model: "nosuch/model", provider: null }), "unsupported_provider"],
  ] as const) {
    const { events } = await runScripted(c, []);
    assert.deepEqual(types(events), ["run_requested", "agent_described", "error_occurred", "agent_stopped"]);
    assert.equal(one(events, "error_occurred").data["avp.error.code"], code);
    assert.equal(one(events, "agent_stopped").data["avp.reason"], "error");
  }
});

test("missing credentials end the run with auth_error after agent_started", async () => {
  model.script([]);
  const sink = new MemorySink();
  await run(commission(), sink, { env: { OPENAI_API_KEY: undefined } });
  const events = JSON.parse(JSON.stringify(sink.events)) as Json[];
  assert.deepEqual(types(events).slice(2), ["agent_started", "error_occurred", "agent_stopped"]);
  assert.equal(one(events, "error_occurred").data["avp.error.code"], "auth_error");
});

test("an abort mid-inference stops the run as interrupted", async () => {
  const controller = new AbortController();
  const timer = setInterval(() => {
    if (model.requests.length > 0) {
      clearInterval(timer);
      setTimeout(() => controller.abort(), 500);
    }
  }, 50);
  const startedAt = Date.now();
  const { events } = await runScripted(commission(), [{ text: "word ".repeat(400), chunkDelayMs: 25 }], {
    signal: controller.signal,
  });
  clearInterval(timer);
  const last = events.at(-1)!;
  assert.equal(last.type, "avp.agent_stopped");
  assert.equal(last.data["avp.reason"], "interrupted");
  assert.ok(Date.now() - startedAt < 8_000, "the abort stopped the stream");
  // What streamed before the cut is reported, without usage.
  const [partial] = all(events, "assistant_message");
  assert.deepEqual(partial["avp.response.finish_reasons"], ["aborted"]);
  assert.match(partial["avp.content"][0].text, /^(word )+/);
  assert.equal(partial["avp.cost.source"], "unknown");
});

test("SIGTERM to the entrypoint closes the trajectory and stops OpenCode", async () => {
  const dir = mkdtempSync(join(tmpdir(), "avp-opencode-cli-"));
  const out = join(dir, "trajectory.ndjson");
  writeFileSync(join(dir, "commission.json"), JSON.stringify(commission()));
  model.script([{ text: "word ".repeat(400), chunkDelayMs: 25 }]);
  const before = servers();
  const main = fileURLToPath(new URL("../src/main.js", import.meta.url));
  const child = spawn(process.execPath, [main, "run", "--commission", join(dir, "commission.json"), "--out", out], {
    cwd: dir,
    env: { ...process.env, OPENAI_API_KEY: "test-key" },
    stdio: "ignore",
  });
  const exited = new Promise<number | null>((resolve) => child.on("exit", (code) => resolve(code)));
  while (model.requests.length === 0) await new Promise((r) => setTimeout(r, 50));
  assert.ok(servers() > before, "the run started an OpenCode server");
  child.kill("SIGTERM");
  assert.equal(await exited, 130);
  const events = readFileSync(out, "utf8").trim().split("\n").map((line) => JSON.parse(line));
  assert.equal(events.at(-1).type, "avp.agent_stopped");
  assert.equal(events.at(-1).data["avp.reason"], "interrupted");
  assert.equal(servers(), before, "no OpenCode server outlives the run");
});

/** Running servers from this package's OpenCode binary. */
function servers(): number {
  const bin = opencodeBinary();
  return execFileSync("ps", ["-A", "-o", "command="], { encoding: "utf8" })
    .split("\n")
    .filter((line) => line.startsWith(`${bin} serve`)).length;
}

test("a task subagent is a closed frame carrying the child's spend", async () => {
  const { events } = await runScripted(commission(), [
    {
      call: {
        id: "call_t",
        name: "task",
        args: { description: "say pong", prompt: "Reply with exactly PONG.", subagent_type: "general" },
      },
    },
    { text: "PONG" },
    { text: "The subagent said PONG." },
  ]);
  assert.deepEqual(types(events).slice(2), [
    "agent_started",
    "assistant_message",
    "tool_invoked",
    "subagent_invoked",
    "subagent_returned",
    "tool_returned",
    "assistant_message",
    "agent_stopped",
  ]);
  const invoked = one(events, "subagent_invoked").data;
  assert.equal(invoked["avp.subagent.name"], "general");
  assert.equal(invoked["avp.subagent.invocation_id"], "call_t");
  const returned = one(events, "subagent_returned").data;
  assert.equal(returned["avp.subagent.reason"], "converged");
  assert.equal(returned["avp.subagent.result.text"], "PONG");
  assert.deepEqual(returned["avp.subagent.usage"], {
    cost_usd: returned["avp.subagent.usage"].cost_usd,
    tokens_input: USAGE.input,
    tokens_output: USAGE.output,
    turns: 1,
  });
  assert.ok(returned["avp.subagent.usage"].cost_usd > 0);
  assert.equal(all(events, "assistant_message").length, 2, "the child's turn is rolled up, not a parent turn");
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("output_schema returns OpenCode's structured output", async () => {
  const schema = { type: "object", properties: { answer: { type: "string" } }, required: ["answer"] };
  const { events } = await runScripted(commission({ output_schema: schema }), [
    { call: { id: "call_s", name: "StructuredOutput", args: { answer: "42" } } },
  ]);
  const stopped = one(events, "agent_stopped").data;
  assert.equal(stopped["avp.reason"], "converged");
  assert.deepEqual(stopped["avp.output"], { answer: "42" });
});

/**
 * Integration tests: the real OpenCode server (the pinned binary), its loop, tools,
 * MCP client, and task subagents, on a scripted OpenAI Responses endpoint,
 * through the adapter, into the Recorder's trajectory. No network.
 */
import { strict as assert } from "node:assert";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

import { MemorySink, type Commission } from "@avp/types";

import { describe, run } from "../src/agent.js";
import { BUILTIN_SKILLS, BUILTIN_SUBAGENTS, keyVar, launcherBaseUrl } from "../src/commission.js";
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
    run_id: "opencode-test",
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

const MCP_ONLY: Partial<Commission> = {
  mcp_servers: [{ type: "stdio", id: "avptest", command: ["python3", FIXTURE] }],
  enabled_builtin_tools: { "avp-opencode": [] },
};

/** A tool_returned's content as text. */
const resultText = (returned: Json) => {
  const content = returned["avp.tool_result"].content;
  return typeof content === "string" ? content : JSON.stringify(content);
};

test("parallel calls in one response pair each result, success or failure, with its own call", async () => {
  const calls = [
    { id: "call_e1", name: "avptest_Avptest_Echo", args: { text: "ECHO-ONE" } },
    { id: "call_f1", name: "avptest_Avptest_Fail", args: { message: "FAIL-RESULT", mode: "result" } },
    { id: "call_e2", name: "avptest_Avptest_Echo", args: { text: "ECHO-TWO" } },
    { id: "call_f2", name: "avptest_Avptest_Fail", args: { message: "FAIL-PROTOCOL", mode: "protocol" } },
  ];
  const { events } = await runScripted(commission(MCP_ONLY), [{ calls }, { text: "DONE" }]);

  const turns = all(events, "assistant_message");
  assert.equal(turns.length, 2, "one turn per model response");
  assert.deepEqual(
    turns[0]["avp.content"].map((b: Json) => [b.type, b.id]),
    calls.map((c) => ["tool_use", c.id]),
  );
  assert.deepEqual(turns[0]["avp.response.finish_reasons"], ["tool-calls"]);

  const invoked = all(events, "tool_invoked").map((d) => d["avp.tool.call_id"]);
  assert.deepEqual(invoked.sort(), calls.map((c) => c.id).sort());
  const returned = all(events, "tool_returned");
  assert.equal(returned.length, calls.length, "one tool_returned per call");
  const byId = new Map(returned.map((d) => [d["avp.tool.call_id"], d]));
  assert.equal(byId.size, calls.length);
  for (const [id, text, isError] of [
    ["call_e1", "ECHO-ONE", false],
    ["call_e2", "ECHO-TWO", false],
    ["call_f1", "FAIL-RESULT", true],
    ["call_f2", "FAIL-PROTOCOL", true],
  ] as const) {
    const result = byId.get(id)!;
    assert.equal(result["avp.tool_result"].is_error, isError, `${id}: ${JSON.stringify(result)}`);
    assert.match(resultText(result), new RegExp(text), id);
    for (const other of ["ECHO-ONE", "ECHO-TWO", "FAIL-RESULT", "FAIL-PROTOCOL"].filter((t) => t !== text)) {
      assert.doesNotMatch(resultText(result), new RegExp(other), `${id} carries another call's result`);
    }
  }
  // Every result follows its call's turn and precedes the next turn.
  const order = types(events);
  const first = order.indexOf("assistant_message");
  const second = order.lastIndexOf("assistant_message");
  order.forEach((t, i) => {
    if (t === "tool_returned") assert.ok(first < i && i < second, `tool_returned at ${i} outside its turn`);
  });
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("parallel calls that finish out of order still pair by call id", async () => {
  const { events } = await runScripted(commission({ enabled_builtin_tools: { "avp-opencode": ["bash"] } }), [
    {
      calls: [
        { id: "call_slow", name: "bash", args: { command: "sleep 1.5; echo SLOW-OUT", description: "slow" } },
        { id: "call_fast", name: "bash", args: { command: "echo FAST-OUT", description: "fast" } },
        { id: "call_mid", name: "bash", args: { command: "sleep 0.5; echo MID-OUT", description: "mid" } },
      ],
    },
    { text: "DONE" },
  ]);
  assert.equal(all(events, "assistant_message").length, 2);
  const returned = all(events, "tool_returned");
  assert.equal(returned.length, 3, "one tool_returned per call");
  const byId = new Map(returned.map((d) => [d["avp.tool.call_id"], d]));
  for (const [id, text, others] of [
    ["call_slow", "SLOW-OUT", ["FAST-OUT", "MID-OUT"]],
    ["call_fast", "FAST-OUT", ["SLOW-OUT", "MID-OUT"]],
    ["call_mid", "MID-OUT", ["SLOW-OUT", "FAST-OUT"]],
  ] as const) {
    const result = byId.get(id)!;
    assert.equal(result["avp.tool_result"].is_error, false, id);
    assert.match(resultText(result), new RegExp(text), id);
    for (const other of others) assert.doesNotMatch(resultText(result), new RegExp(other), id);
  }
  // Results land in completion order, each at its own end time, so a fast
  // call's duration is not stretched to the slowest call's.
  const returnedEvents = events.filter((e) => e.type === "avp.tool_returned");
  assert.deepEqual(
    returnedEvents.map((e) => e.data["avp.tool.call_id"]),
    ["call_fast", "call_mid", "call_slow"],
  );
  const invokedAt = Date.parse(events.find((e) => e.type === "avp.tool_invoked")!.time);
  const [fast, mid, slow] = returnedEvents.map((e) => Date.parse(e.time) - invokedAt);
  assert.ok(fast! < 400 && mid! >= 400 && mid! < 1400 && slow! >= 1400, `durations ${fast}/${mid}/${slow}ms`);
  const times = events.map((e) => Date.parse(e.time));
  times.slice(1).forEach((t, i) => assert.ok(t >= times[i]!, `event ${i + 1} is earlier than event ${i}`));
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("dependent rounds are one turn per model response, each with its own usage", async () => {
  const usages = [
    { input: 100, cached: 10, output: 11 },
    { input: 200, cached: 20, output: 22 },
    { input: 300, cached: 30, output: 33 },
  ];
  const { events } = await runScripted(commission(MCP_ONLY), [
    { call: { id: "call_a1", name: "avptest_Avptest_Add", args: { a: 2, b: 3 } }, usage: usages[0] },
    { call: { id: "call_a2", name: "avptest_Avptest_Add", args: { a: 5, b: 4 } }, usage: usages[1] },
    { text: "The total is 9.", usage: usages[2] },
  ]);
  assert.deepEqual(types(events).slice(2), [
    "agent_started",
    "assistant_message",
    "tool_invoked",
    "tool_returned",
    "assistant_message",
    "tool_invoked",
    "tool_returned",
    "assistant_message",
    "agent_stopped",
  ]);
  // Each round's request carried the previous round's result.
  assert.equal(model.requests.length, 3);
  assert.match(JSON.stringify(model.requests[1]!.input), /sum: 5/);
  assert.match(JSON.stringify(model.requests[2]!.input), /sum: 9/);

  const turns = all(events, "assistant_message");
  turns.forEach((turn, i) => {
    assert.deepEqual(turn["avp.usage"], {
      input_tokens: usages[i]!.input,
      output_tokens: usages[i]!.output,
      cache_read_input_tokens: usages[i]!.cached,
      cache_creation_input_tokens: 0,
    });
    assert.equal(turn["avp.cost.source"], "computed");
  });
  assert.deepEqual(turns[0]["avp.content"].map((b: Json) => b.id), ["call_a1"]);
  assert.deepEqual(turns[1]["avp.content"].map((b: Json) => b.id), ["call_a2"]);
  assert.deepEqual(turns[2]["avp.content"], [{ type: "text", text: "The total is 9." }]);

  const returned = all(events, "tool_returned");
  assert.deepEqual(
    returned.map((d) => [d["avp.tool.call_id"], d["avp.tool_result"].is_error]),
    [
      ["call_a1", false],
      ["call_a2", false],
    ],
  );
  assert.match(resultText(returned[0]!), /sum: 5/);
  assert.match(resultText(returned[1]!), /sum: 9/);
  const stopped = one(events, "agent_stopped").data;
  assert.equal(stopped["avp.reason"], "converged");
  assert.equal(stopped["avp.output"], "The total is 9.");
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
    [commission({ model: "nosuch/model", provider: null }), "unsupported_provider"],
  ] as const) {
    const { events } = await runScripted(c, []);
    assert.deepEqual(types(events), ["run_requested", "agent_described", "error_occurred", "agent_stopped"]);
    assert.equal(one(events, "error_occurred").data["avp.error.code"], code);
    assert.equal(one(events, "agent_stopped").data["avp.reason"], "error");
  }
});

test("a model newer than the bundled catalog runs on its provider's SDK", async () => {
  const { events } = await runScripted(commission({ model: "openai/gpt-from-the-future" }), [{ text: "DONE" }]);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
  assert.equal(one(events, "agent_stopped").data["avp.output"], "DONE");
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

test("the launcher's <PROVIDER>_HOST routes the provider, keeping its SDK's version path", async () => {
  assert.equal(launcherBaseUrl("anthropic", { ANTHROPIC_HOST: "http://b/llm/anthropic/" }), "http://b/llm/anthropic/v1");
  assert.equal(launcherBaseUrl("google", { GOOGLE_HOST: "http://b/llm/google" }), "http://b/llm/google/v1beta");
  assert.equal(launcherBaseUrl("openai", {}), undefined);

  const cwd = mkdtempSync(join(tmpdir(), "avp-opencode-ws-"));
  model.script([{ text: "routed" }]);
  const sink = new MemorySink();
  const previous = process.cwd();
  process.chdir(cwd);
  try {
    const { provider: _, ...unrouted } = commission();
    await run(unrouted as Commission, sink, {
      env: { OPENAI_API_KEY: "test-key", OPENAI_HOST: model.baseUrl.replace(/\/v1$/, "") },
    });
  } finally {
    process.chdir(previous);
  }
  const events: Json[] = JSON.parse(JSON.stringify(sink.events));
  assert.equal(model.requests.length, 1);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("a launcher's GEMINI_API_KEY authenticates Google", async () => {
  assert.equal(keyVar("google", { GOOGLE_GENERATIVE_AI_API_KEY: "a", GEMINI_API_KEY: "b" }), undefined);
  assert.equal(keyVar("google", { GOOGLE_API_KEY: "c" }), "GOOGLE_API_KEY");
  assert.equal(keyVar("openai", { GEMINI_API_KEY: "b" }), undefined);

  const keys: (string | undefined)[] = [];
  const gemini = createServer((req, res) => {
    keys.push(req.headers["x-goog-api-key"] as string | undefined);
    req.resume();
    res.writeHead(200, { "content-type": "text/event-stream" });
    const chunk = {
      candidates: [{ content: { role: "model", parts: [{ text: "routed" }] }, finishReason: "STOP", index: 0 }],
      usageMetadata: { promptTokenCount: 12, candidatesTokenCount: 3, totalTokenCount: 15 },
    };
    res.end(`data: ${JSON.stringify(chunk)}\n\n`);
  });
  await new Promise<void>((resolve) => gemini.listen(0, "127.0.0.1", resolve));
  const { port } = gemini.address() as AddressInfo;
  const cwd = mkdtempSync(join(tmpdir(), "avp-opencode-ws-"));
  const sink = new MemorySink();
  const previous = process.cwd();
  process.chdir(cwd);
  try {
    const { provider: _, ...unrouted } = commission();
    await run({ ...unrouted, model: "google/gemini-3.1-flash-lite" } as Commission, sink, {
      env: {
        GOOGLE_GENERATIVE_AI_API_KEY: "",
        GEMINI_API_KEY: "launcher-key",
        GOOGLE_HOST: `http://127.0.0.1:${port}`,
      },
    });
  } finally {
    process.chdir(previous);
    gemini.close();
  }
  const events: Json[] = JSON.parse(JSON.stringify(sink.events));
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
  assert.ok(keys.length > 0 && keys.every((k) => k === "launcher-key"), `keys sent: ${JSON.stringify(keys)}`);
});

test("caller OpenTelemetry settings reach native tool subprocesses", async () => {
  const previous = process.env.OTEL_SERVICE_NAME;
  process.env.OTEL_SERVICE_NAME = "avp-caller-service";
  try {
    const { events, cwd } = await runScripted(commission(), (workspace) => [
      { call: { id: "call_env", name: "bash", args: {
        command: `printenv OTEL_SERVICE_NAME > '${join(workspace, "otel.txt")}'`,
        description: "Read the caller's service name",
      } } },
      { text: "DONE" },
    ]);
    assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
    assert.equal(readFileSync(join(cwd, "otel.txt"), "utf8").trim(), "avp-caller-service");
  } finally {
    if (previous === undefined) delete process.env.OTEL_SERVICE_NAME;
    else process.env.OTEL_SERVICE_NAME = previous;
  }
});

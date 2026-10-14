/**
 * Seam tests: Gemini CLI's real headless session, tool scheduler, built-in
 * tools, and MCP client on its own scripted content generator
 * (`FakeContentGenerator`, what `gemini --fake-responses` replays), through
 * the adapter, into the Recorder's trajectory. No network.
 */
import { strict as assert } from "node:assert";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { MemorySink, type Commission } from "@avp/types";
import { FakeContentGenerator, type ContentGenerator } from "@google/gemini-cli-core";

import { run } from "../src/agent.js";
import { errorCode } from "../src/translate.js";

type Json = Record<string, any>;

const MODEL = "gemini-2.5-flash";

// Gemini CLI wants a Gemini API key to configure its client; the scripted
// generator replaces that client, so the key is never sent anywhere.
process.env.GEMINI_API_KEY ??= "test-key";

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
    run_id: "gemini-cli-seam",
    model: `google/${MODEL}`,
    prompt: "do the thing",
    ...extra,
  } as Commission;
}

/** One streamed model response: its parts, finish reason, and usage. */
function response(parts: Json[], usage: Json = {}): Json[] {
  return [
    {
      candidates: [{ content: { role: "model", parts }, finishReason: "STOP", index: 0 }],
      usageMetadata: { promptTokenCount: 120, candidatesTokenCount: 8, totalTokenCount: 128, ...usage },
      modelVersion: MODEL,
    },
  ];
}

const call = (id: string, name: string, args: Json) => ({ functionCall: { id, name, args } });

/** Gemini CLI's scripted generator over `responses`, one per model call. */
function scripted(responses: Json[][]): FakeContentGenerator {
  return new FakeContentGenerator(responses.map((r) => ({ method: "generateContentStream", response: r })) as never);
}

/** Run the adapter in a fresh workspace on `generator`. */
async function runWith(
  c: Commission,
  generator: ContentGenerator,
  opts: { signal?: AbortSignal } = {},
): Promise<{ events: Json[]; cwd: string }> {
  const cwd = mkdtempSync(join(tmpdir(), "avp-gemini-cli-ws-"));
  const sink = new MemorySink();
  const previous = process.cwd();
  process.chdir(cwd);
  try {
    await run(c, sink, { contentGenerator: generator, signal: opts.signal });
  } finally {
    process.chdir(previous);
  }
  return { events: JSON.parse(JSON.stringify(sink.events)), cwd };
}

const types = (events: Json[]) => events.map((e) => e.type.replace(/^avp\./, ""));
const one = (events: Json[], type: string) => events.find((e) => e.type === `avp.${type}`)!;
const all = (events: Json[], type: string) => events.filter((e) => e.type === `avp.${type}`).map((e) => e.data);

test("a built-in tool round trip is one turn per response with paired tool events", async () => {
  const { events, cwd } = await runWith(
    commission(),
    scripted([
      response(
        [
          { text: "Checking the plan.", thought: true },
          call("w1", "write_file", { file_path: "out.txt", content: "OK" }),
        ],
        { thoughtsTokenCount: 30, cachedContentTokenCount: 100 },
      ),
      response([{ text: "DONE" }], { promptTokenCount: 200 }),
    ]),
  );
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
    one(events, "agent_described").data["avp.descriptor"].tools.map((t: Json) => t.name),
  );
  assert.deepEqual(
    started["avp.subagents"].map((s: Json) => s.name),
    ["codebase_investigator", "cli_help", "generalist"],
  );
  const invoked = one(events, "tool_invoked").data;
  assert.equal(invoked["avp.tool.name"], "write_file");
  assert.equal(invoked["avp.tool.dispatch_target"], "local");
  const returned = one(events, "tool_returned").data;
  assert.equal(returned["avp.tool.call_id"], "write_file__w1");
  assert.equal(returned["avp.tool_result"].is_error, false);
  assert.match(JSON.stringify(returned["avp.tool_result"].content), /out\.txt/);

  const [first, second] = all(events, "assistant_message");
  assert.deepEqual(first["avp.content"], [
    { type: "thinking", thinking: "Checking the plan." },
    { type: "tool_use", id: "write_file__w1", name: "write_file", input: { file_path: "out.txt", content: "OK" } },
  ]);
  // Gemini's prompt count already holds the cache; thoughts are output too.
  assert.deepEqual(first["avp.usage"], {
    input_tokens: 120,
    output_tokens: 38,
    cache_read_input_tokens: 100,
    reasoning_output_tokens: 30,
  });
  assert.deepEqual(first["avp.response.finish_reasons"], ["STOP"]);
  for (const turn of [first, second]) {
    assert.equal(turn["avp.cost.source"], "computed");
    assert.equal(turn["avp.response.model"], MODEL);
    assert.ok(turn["avp.cost_usd"] > 0);
  }
  assert.equal(second["avp.usage"].input_tokens, 200);
  const stopped = one(events, "agent_stopped").data;
  assert.equal(stopped["avp.reason"], "converged");
  assert.equal(stopped["avp.output"], "DONE");
});

test("Commission MCP tools run through Gemini CLI's MCP client", async () => {
  const { events } = await runWith(
    commission({
      mcp_servers: [{ type: "stdio", id: "avptest", command: ["python3", FIXTURE] }],
      enabled_builtin_tools: { "avp-gemini-cli": [] },
    }),
    scripted([
      response([call("m1", "mcp_avptest_Avptest_Echo", { text: "AVP-MCP" })]),
      response([{ text: "AVP-MCP" }]),
    ]),
  );
  const started = one(events, "agent_started").data;
  assert.deepEqual(started["avp.mcp_servers"], [{ id: "avptest", status: "connected" }]);
  const echo = started["avp.tools"].find((t: Json) => t.name === "mcp_avptest_Avptest_Echo");
  assert.equal(echo["avp.mcp_server_id"], "avptest");
  assert.ok(!started["avp.tools"].some((t: Json) => t.name === "write_file"), "empty allow-list hides built-ins");

  const invoked = one(events, "tool_invoked").data;
  assert.equal(invoked["avp.tool.dispatch_target"], "mcp_server");
  const result = one(events, "tool_returned").data["avp.tool_result"];
  assert.equal(result.is_error, false);
  assert.match(JSON.stringify(result.content), /AVP-MCP/);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("a subagent runs in a frame closed before its tool result, with its spend rolled up", async () => {
  const { events } = await runWith(
    commission(),
    scripted([
      response([call("a1", "invoke_agent", { agent_name: "generalist", prompt: "Reply with PONG." })]),
      // The generalist's own model call, finishing its task.
      response([call("c1", "complete_task", { result: { response: "PONG" } })], {
        promptTokenCount: 50,
        candidatesTokenCount: 5,
      }),
      response([{ text: "PONG" }]),
    ]),
  );
  assert.deepEqual(types(events).slice(3), [
    "assistant_message",
    "tool_invoked",
    "subagent_invoked",
    "subagent_returned",
    "tool_returned",
    "assistant_message",
    "agent_stopped",
  ]);
  const invoked = one(events, "subagent_invoked").data;
  assert.equal(invoked["avp.subagent.name"], "generalist");
  assert.equal(invoked["avp.subagent.invocation_id"], "invoke_agent__a1");
  const returned = one(events, "subagent_returned").data;
  assert.equal(returned["avp.subagent.reason"], "converged");
  assert.match(returned["avp.subagent.result.text"], /PONG/);
  const usage = returned["avp.subagent.usage"];
  assert.equal(usage.tokens_input, 50);
  assert.equal(usage.tokens_output, 5);
  assert.equal(usage.turns, 1);
  assert.ok(usage.cost_usd > 0);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("the system prompt, inline skills, and built-in allow-lists reach Gemini CLI", async () => {
  const { events } = await runWith(
    commission({
      system_prompt: "Always answer in haiku. AVP-SYSTEM-7Q.",
      skills: [
        {
          id: "avp-codeword",
          files: { "SKILL.md": "---\nname: avp-codeword\ndescription: The AVP codeword.\n---\n\nThe codeword is X.\n" },
        },
      ],
      enabled_builtin_subagents: { "avp-gemini-cli": ["generalist"] },
      enabled_builtin_skills: { "avp-gemini-cli": [] },
    }),
    scripted([response([{ text: "ok" }])]),
  );
  const started = one(events, "agent_started").data;
  assert.match(started["avp.system_prompt"], /AVP-SYSTEM-7Q/);
  assert.deepEqual(
    started["avp.skills"].map((s: Json) => s.name),
    ["avp-codeword"],
  );
  assert.deepEqual(
    started["avp.subagents"].map((s: Json) => s.name),
    ["generalist"],
  );
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("an MCP server that fails to connect is reported and left out", async () => {
  const { events } = await runWith(
    commission({ mcp_servers: [{ type: "stdio", id: "broken", command: ["/nonexistent/avp-mcp"] }] }),
    scripted([response([{ text: "fine" }])]),
  );
  assert.deepEqual(types(events).slice(0, 4), ["run_requested", "agent_described", "error_occurred", "agent_started"]);
  assert.equal(one(events, "error_occurred").data["avp.error.code"], "mcp_connect_failed");
  assert.deepEqual(one(events, "agent_started").data["avp.mcp_servers"], [{ id: "broken", status: "failed" }]);
  assert.equal(one(events, "agent_stopped").data["avp.reason"], "converged");
});

test("a provider failure ends the run with a classified error and no turn", async () => {
  for (const [status, message, code] of [
    [400, "API key not valid. Please pass a valid API key.", "auth_error"],
    [400, "The input token count (1200000) exceeds the maximum number of tokens allowed (1048576).", "context_limit"],
  ] as const) {
    const failing: ContentGenerator = {
      async generateContent() {
        throw Object.assign(new Error(message), { status });
      },
      async generateContentStream() {
        throw Object.assign(new Error(message), { status });
      },
      async countTokens() {
        return { totalTokens: 0 };
      },
      async embedContent() {
        throw new Error("unused");
      },
    };
    const { events } = await runWith(commission(), failing);
    const error = one(events, "error_occurred").data;
    assert.equal(error["avp.error.code"], code, message);
    assert.equal(one(events, "agent_stopped").data["avp.reason"], "error");
    assert.ok(!types(events).includes("assistant_message"), "a failed inference is not a turn");
  }
});

test("provider failure messages classify as auth, rate limit, and context limit", () => {
  assert.equal(errorCode("API key not valid. Please pass a valid API key.", 400), "auth_error");
  assert.equal(errorCode("Resource has been exhausted (e.g. check quota).", 429), "rate_limit");
  assert.equal(errorCode("You exceeded your current quota, please check your plan and billing details."), "rate_limit");
  assert.equal(errorCode("models/gemini-nope is not found for API version v1beta", 404), "unsupported_model");
  assert.equal(errorCode("socket hang up"), "unknown");
});

test("a Commission the agent cannot honor fails fast before agent_started", async () => {
  for (const [c, code] of [
    [commission({ enabled_builtin_tools: { "avp-gemini-cli": ["fly"] } }), "commission_collision"],
    [commission({ enabled_builtin_subagents: { "avp-gemini-cli": ["nobody"] } }), "commission_collision"],
    [commission({ agent_versions: { "avp-gemini-cli": "9.9.9" } }), "unsupported_agent_version"],
    [commission({ model: "anthropic/claude-haiku-4-5" }), "unsupported_model"],
    [commission({ provider: { id: "openrouter" } }), "unsupported_provider"],
  ] as const) {
    const { events } = await runWith(c, scripted([]));
    assert.deepEqual(types(events), ["run_requested", "agent_described", "error_occurred", "agent_stopped"]);
    assert.equal(one(events, "error_occurred").data["avp.error.code"], code);
    assert.equal(one(events, "agent_stopped").data["avp.reason"], "error");
  }
});

test("an abort mid-inference stops the run as interrupted", async () => {
  const fake = scripted([
    Array.from({ length: 40 }, (_, i) => ({
      candidates: [{ content: { role: "model", parts: [{ text: `word${i} ` }] }, index: 0 }],
      modelVersion: MODEL,
    })),
  ]);
  // Gemini CLI's scripted stream, slowed to one chunk per 50 ms.
  const slow: ContentGenerator = {
    generateContent: (...a) => fake.generateContent(...a),
    countTokens: (...a) => fake.countTokens(...a),
    embedContent: (...a) => fake.embedContent(...a),
    async generateContentStream(...a) {
      const stream = await fake.generateContentStream(...a);
      return (async function* () {
        for await (const chunk of stream) {
          await new Promise((r) => setTimeout(r, 50));
          yield chunk;
        }
      })();
    },
  };
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 300);
  const { events } = await runWith(commission(), slow, { signal: controller.signal });
  const last = events.at(-1)!;
  assert.equal(last.type, "avp.agent_stopped");
  assert.equal(last.data["avp.reason"], "interrupted");
  assert.ok(types(events).includes("agent_started"));
  assert.ok(!types(events).includes("assistant_message"), "the cut-off response is not a turn");
});

import type { JsonValue } from "@agent-voyager-project/sdk/reports";
/** Native Pi sessions and MCP clients produce validated SDK Trajectories. */
import { strict as assert } from "node:assert";
import { randomUUID } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import {
  parseTrajectory,
  type Trajectory,
} from "@agent-voyager-project/sdk/trajectory";
import {
  getSystemMessageText,
  fauxAssistantMessage,
  fauxProvider,
  fauxText,
  fauxThinking,
  fauxToolCall,
  type FauxResponseStep,
} from "@earendil-works/pi-ai";
import { run } from "../src/agent.js";
import { describe, runtime } from "../src/descriptor.js";

const MODEL = "claude-haiku-4-5";
const fixture = fileURLToPath(
  new URL("../../../../../testing/mcp/avp_test_mcp.py", import.meta.url),
);
function received(extra = {}): JsonValue {
  return {
    avp_version: "0.1",
    run_id: "pi-test",
    model: { provider: "anthropic", id: MODEL },
    prompt: "Say DONE",
    ...extra,
  };
}

function latest(snapshots: Trajectory[]): any {
  return snapshots.at(-1)!;
}
function meta(value: any): any {
  return value.extra?.avp ?? {};
}
function docs(root: any): any[] {
  return [root, ...(root.subagent_trajectories ?? []).flatMap(docs)];
}
function atifResponses(snapshots: Trajectory[]): any[] {
  return docs(latest(snapshots))
    .flatMap((d) => d.steps.filter((s: any) => s.source === "agent"))
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
}
function atifCalls(snapshots: Trajectory[]): any[] {
  return atifResponses(snapshots).flatMap((s) => s.tool_calls ?? []);
}
function atifResults(snapshots: Trajectory[]): any[] {
  return docs(latest(snapshots))
    .flatMap((d) => d.steps.flatMap((s: any) => s.observation?.results ?? []))
    .filter((r) => r.content !== undefined);
}
function atifErrors(snapshots: Trajectory[]): any[] {
  return docs(latest(snapshots)).flatMap((d) =>
    d.steps.filter((s: any) => meta(s).error_code),
  );
}
function atifChildren(snapshots: Trajectory[]): any[] {
  return docs(latest(snapshots)).slice(1);
}

async function scripted(
  commission: JsonValue,
  responses: FauxResponseStep[],
  options: {
    signal?: AbortSignal;
    slowSink?: boolean;
    tokensPerSecond?: number;
  } = {},
) {
  const cwd = mkdtempSync(join(tmpdir(), "avp-pi-ws-"));
  const models = await runtime();
  const faux = fauxProvider({
    provider: "anthropic",
    models: [{ id: MODEL }],
    tokensPerSecond: options.tokensPerSecond,
  });
  faux.setResponses(responses);
  models.registerNativeProvider(faux.provider);
  await models.setRuntimeApiKey("anthropic", "fixture-stand-in");
  const snapshots: Trajectory[] = [];
  const before = process.cwd();
  process.chdir(cwd);
  try {
    await run(
      commission,
      async (event) => {
        if (options.slowSink) await delay(5);
        const parsed = parseTrajectory(event.trajectory);
        assert.ok(parsed);
        snapshots.push(parsed);
      },
      options.signal ?? new AbortController().signal,
      { modelRuntime: models },
    );
    if (process.env.AVP_ATIF_CAPTURE) {
      writeFileSync(
        join(process.env.AVP_ATIF_CAPTURE, `${randomUUID()}.json`),
        JSON.stringify(latest(snapshots)) + "\n",
      );
    }
    return { snapshots, cwd, faux };
  } finally {
    process.chdir(before);
    rmSync(cwd, { force: true, recursive: true });
  }
}
const text = (value = "DONE") => fauxAssistantMessage([fauxText(value)]);

test("native responses retain reasoning, skills, replacement instructions, and per-response usage", async () => {
  let system: string | undefined;
  const { snapshots } = await scripted(
    received({
      system_prompt: "SYSTEM",
      skills: [
        {
          name: "greeting",
          files: {
            "SKILL.md":
              "---\nname: greeting\ndescription: Greeting\n---\nGREETING",
            "support.txt": "SUPPORT",
          },
        },
      ],
    }),
    [
      (context) => {
        system = context.messages
          .filter((m) => m.role === "system")
          .map(getSystemMessageText)
          .join("\n\n");
        return fauxAssistantMessage([
          fauxThinking("THOUGHT"),
          fauxText("DONE"),
        ]);
      },
    ],
  );
  assert.equal(atifResponses(snapshots).length, 1);
  assert.equal(meta(latest(snapshots)).complete, true);
  assert.ok(system?.startsWith("SYSTEM"));
  assert.ok(system?.includes("<available_skills>"));
  assert.ok(system?.includes("<name>greeting</name>"));
  assert.ok(!system?.includes("GREETING"));
  assert.ok(!system?.includes("SUPPORT"));
  assert.ok(!system?.includes("You are an expert coding assistant"));
  assert.equal(
    latest(snapshots).steps.find((s: any) => s.source === "system")?.message,
    system,
  );
  const response = atifResponses(snapshots)[0]!;
  assert.equal(response.reasoning_content, "THOUGHT");
  assert.ok(
    response.metrics.prompt_tokens > 0 &&
      response.metrics.completion_tokens > 0,
  );
  assert.equal(meta(latest(snapshots)).output, "DONE");
});

test("native filesystem and bash tools complete with ordered asynchronous sink writes", async () => {
  const { snapshots } = await scripted(
    received(),
    [
      fauxAssistantMessage(
        [
          fauxToolCall(
            "write",
            { path: "answer.txt", content: "BOUNDARY" },
            { id: "write" },
          ),
        ],
        { stopReason: "toolUse" },
      ),
      fauxAssistantMessage(
        [fauxToolCall("bash", { command: "cat answer.txt" }, { id: "read" })],
        { stopReason: "toolUse" },
      ),
      text(),
    ],
    { slowSink: true },
  );
  assert.equal(atifResponses(snapshots).length, 3);
  const returns = atifResults(snapshots);
  assert.deepEqual(
    returns.map((e) => e.source_call_id),
    ["write", "read"],
  );
  assert.match(JSON.stringify(returns[1]!.content), /BOUNDARY/);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
  for (const result of returns) {
    const called = snapshots.findIndex((s) =>
      atifCalls([s]).some((c) => c.tool_call_id === result.source_call_id),
    );
    const returned = snapshots.findIndex((s) =>
      atifResults([s]).some((r) => r.source_call_id === result.source_call_id),
    );
    assert.ok(called >= 0 && returned > called);
  }
});

test("disabled built-ins are absent from the model and refused if called", async () => {
  const { snapshots } = await scripted(
    received({ agents: { "avp-pi": { enabled_tools: [] } } }),
    [
      fauxAssistantMessage(
        [
          fauxToolCall(
            "bash",
            { command: "touch MUST_NOT_EXIST" },
            { id: "denied" },
          ),
        ],
        { stopReason: "toolUse" },
      ),
      text(),
    ],
  );
  assert.deepEqual(latest(snapshots).agent.tool_definitions, []);
  assert.equal(meta(atifResults(snapshots)[0]!).is_error, true);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

for (const mode of ["parallel", "errors"] as const)
  test(`native MCP ${mode} calls retain ownership and pair by call ID`, async () => {
    const calls = [
      fauxToolCall(
        "mcp__fixture__Avptest_Echo",
        { text: "BOUNDARY" },
        { id: "echo" },
      ),
    ];
    if (mode === "parallel")
      calls.push(
        fauxToolCall(
          "mcp__fixture__Avptest_Add",
          { a: 2, b: 3 },
          { id: "sum" },
        ),
      );
    else
      calls.push(
        fauxToolCall(
          "mcp__fixture__Avptest_Fail",
          { message: "BAD-RESULT", mode: "result" },
          { id: "result" },
        ),
        fauxToolCall(
          "mcp__fixture__Avptest_Fail",
          { message: "BAD-PROTOCOL", mode: "protocol" },
          { id: "protocol" },
        ),
      );
    const { snapshots } = await scripted(
      received({
        agents: { "avp-pi": { enabled_tools: [] } },
        mcp_servers: [
          { type: "stdio", id: "fixture", command: ["python3", fixture] },
        ],
      }),
      [fauxAssistantMessage(calls, { stopReason: "toolUse" }), text()],
    );
    const invoked = atifCalls(snapshots);
    const returned = atifResults(snapshots);
    assert.equal(invoked.length, calls.length);
    assert.equal(returned.length, calls.length);
    assert.ok(invoked.every((e) => meta(e).mcp_server_id === "fixture"));
    assert.match(
      JSON.stringify(
        returned.find((e) => e.source_call_id === "echo")!.content,
      ),
      /BOUNDARY/,
    );
    if (mode === "errors") {
      assert.equal(
        meta(returned.find((e) => e.source_call_id === "result")!).is_error,
        true,
      );
      assert.equal(
        meta(returned.find((e) => e.source_call_id === "protocol")!).is_error,
        true,
      );
    }
    assert.equal(atifResponses(snapshots).length, 2);
    assert.equal(meta(latest(snapshots)).stop_reason, "converged");
  });

for (const fields of [
  { agents: { other: {} } },
  { agents: { "avp-pi": { enabled_tools: ["missing"] } } },
  { output_schema: { type: "object" } },
  { model: { provider: "missing", id: "missing" } },
])
  test(`unusable Commission stops before any model call: ${JSON.stringify(fields)}`, async () => {
    const { snapshots, faux } = await scripted(received(fields), []);
    assert.equal(atifResponses(snapshots).length, 0);
    assert.equal(meta(latest(snapshots)).complete, true);
    assert.equal(
      meta(atifErrors(snapshots)[0]!).error_code,
      "invalid_commission",
    );
    assert.equal(faux.state.callCount, 0);
  });

test("missing environment credentials stop as auth_error", async () => {
  delete process.env.MISSING_AVP_PI_KEY;
  const { snapshots } = await scripted(
    received({
      model: {
        provider: "anthropic",
        id: MODEL,
        credential: { env: "MISSING_AVP_PI_KEY" },
      },
    }),
    [],
  );
  assert.equal(meta(atifErrors(snapshots)[0]!).error_code, "auth_error");
});

test("unreachable MCP server stops before model execution", async () => {
  const { snapshots, faux } = await scripted(
    received({
      mcp_servers: [
        { type: "stdio", id: "bad", command: ["/nonexistent/mcp"] },
      ],
    }),
    [],
  );
  assert.equal(
    meta(atifErrors(snapshots)[0]!).error_code,
    "mcp_connect_failed",
  );
  assert.equal(faux.state.callCount, 0);
});

test("provider errors are terminal errors rather than synthetic model responses", async () => {
  const { snapshots } = await scripted(received(), [
    fauxAssistantMessage([], {
      stopReason: "error",
      errorMessage: "401 authentication failed",
    }),
  ]);
  assert.equal(atifResponses(snapshots).length, 0);
  assert.equal(meta(atifErrors(snapshots)[0]!).error_code, "auth_error");
  assert.equal(meta(latest(snapshots)).stop_reason, "error");
});

test("cancelling a native streamed response closes the run as interrupted", async () => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 150);
  try {
    const { snapshots } = await scripted(
      received(),
      [text("A long streamed response to interrupt")],
      { signal: controller.signal, tokensPerSecond: 2 },
    );
    assert.equal(meta(latest(snapshots)).stop_reason, "interrupted");
  } finally {
    clearTimeout(timer);
  }
});

test("CLI ping stays lazy and the descriptor lists native default tools", async () => {
  const entry = fileURLToPath(new URL("../src/main.js", import.meta.url));
  assert.equal(
    JSON.parse(
      execFileSync(process.execPath, [entry, "ping"], { encoding: "utf8" }),
    ).type,
    "pong",
  );
  const descriptor = await describe();
  assert.deepEqual(
    descriptor.tools?.map((t) => t.name),
    ["read", "bash", "edit", "write"],
  );
  assert.ok(
    descriptor.supported_models?.some((m) => m.provider === "anthropic"),
  );
  assert.equal(descriptor.subagents, undefined);
});

test("native MCP structured output, environment references, and colliding names survive", async () => {
  const before = process.env.AVP_TEST_PI_CREDENTIAL;
  process.env.AVP_TEST_PI_CREDENTIAL = "fixture-env-value";
  try {
    const path = fileURLToPath(
      new URL("../../tests/fixtures/mcp.mjs", import.meta.url),
    );
    let names: string[] = [];
    const { snapshots } = await scripted(
      received({
        agents: { "avp-pi": { enabled_tools: [] } },
        mcp_servers: ["same-name", "same_name"].map((id) => ({
          type: "stdio",
          id,
          command: [process.execPath, path],
          env: { AVP_TEST_MCP_CREDENTIAL: { env: "AVP_TEST_PI_CREDENTIAL" } },
        })),
      }),
      [
        (context) => {
          names = context.messages
            .flatMap((m) => (m.role === "system" ? (m.toolsAdded ?? []) : []))
            .map((t) => t.name);
          return fauxAssistantMessage(
            names.map((name, i) =>
              fauxToolCall(name, {}, { id: `structured-${i}` }),
            ),
            { stopReason: "toolUse" },
          );
        },
        text(),
      ],
    );
    assert.equal(names.length, 2);
    assert.equal(new Set(names).size, 2);
    assert.ok(names.every((name) => name.length <= 64));
    const results = atifResults(snapshots);
    assert.equal(results.length, 2);
    assert.ok(
      results.every(
        (result) =>
          meta(result).structured_content?.value === "fixture-env-value",
      ),
    );
    assert.deepEqual(
      new Set(atifCalls(snapshots).map((call) => meta(call).mcp_server_id)),
      new Set(["same-name", "same_name"]),
    );
    assert.equal(meta(latest(snapshots)).stop_reason, "converged");
  } finally {
    if (before === undefined) delete process.env.AVP_TEST_PI_CREDENTIAL;
    else process.env.AVP_TEST_PI_CREDENTIAL = before;
  }
});

test("native Anthropic HTTP requests use the proxy key and retain cache-inclusive usage", async () => {
  const { createServer } = await import("node:http");
  let key: string | string[] | undefined;
  const server = createServer((request, response) => {
    key = request.headers["x-api-key"];
    request.resume();
    const frames = [
      {
        type: "message_start",
        message: {
          id: "native-response",
          type: "message",
          role: "assistant",
          model: "claude-haiku-4-5-20251001",
          content: [],
          stop_reason: null,
          stop_sequence: null,
          usage: {
            input_tokens: 600,
            cache_read_input_tokens: 300,
            cache_creation_input_tokens: 100,
            output_tokens: 0,
          },
        },
      },
      {
        type: "content_block_start",
        index: 0,
        content_block: { type: "text", text: "" },
      },
      {
        type: "content_block_delta",
        index: 0,
        delta: { type: "text_delta", text: "DONE" },
      },
      { type: "content_block_stop", index: 0 },
      {
        type: "message_delta",
        delta: { stop_reason: "end_turn", stop_sequence: null },
        usage: { output_tokens: 50 },
      },
      { type: "message_stop" },
    ];
    response.writeHead(200, { "content-type": "text/event-stream" });
    response.end(
      frames
        .map(
          (frame) => `event: ${frame.type}\ndata: ${JSON.stringify(frame)}\n\n`,
        )
        .join(""),
    );
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const snapshots: Trajectory[] = [];
  try {
    await run(
      received({
        model: {
          provider: "anthropic",
          id: MODEL,
          base_url: `http://127.0.0.1:${address.port}`,
          credential: { proxy: "fixture" },
        },
        agents: { "avp-pi": { enabled_tools: [] } },
      }),
      async (event) => {
        snapshots.push(parseTrajectory(event.trajectory));
      },
      new AbortController().signal,
    );
    assert.equal(key, "avp-proxy-stand-in");
    const response = atifResponses(snapshots)[0]!;
    assert.equal(response.metrics.prompt_tokens, 1000);
    assert.equal(response.metrics.completion_tokens, 50);
    assert.equal(response.metrics.cached_tokens, 300);
    assert.equal(meta(response.metrics).cache_creation_input_tokens, 100);
    assert.equal(response.model_name, "claude-haiku-4-5-20251001");
    assert.deepEqual(meta(response).finish_reasons, ["end_turn"]);
    assert.equal(meta(latest(snapshots)).stop_reason, "converged");
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});

test("Pi loads commissioned skills and support files on demand through its native reader", async () => {
  let skillPath = "";
  const { snapshots } = await scripted(
    received({
      system_prompt: "Use the matching skill.",
      skills: [
        {
          name: "greeting",
          files: {
            "SKILL.md":
              "---\nname: greeting\ndescription: Greeting\n---\nRead support.txt for the answer.",
            "support.txt": "NATIVE_SKILL_RESULT",
          },
        },
      ],
    }),
    [
      (context) => {
        const prompt = context.messages
          .filter((m) => m.role === "system")
          .map(getSystemMessageText)
          .join("\n");
        assert.ok(!prompt.includes("NATIVE_SKILL_RESULT"));
        const match = prompt.match(/<location>([^<]+)<\/location>/);
        assert.ok(match);
        skillPath = match[1]!;
        return fauxAssistantMessage(
          [fauxToolCall("read", { path: skillPath }, { id: "skill" })],
          { stopReason: "toolUse" },
        );
      },
      (context) => {
        assert.ok(
          JSON.stringify(context.messages).includes(
            "Read support.txt for the answer.",
          ),
        );
        return fauxAssistantMessage(
          [
            fauxToolCall(
              "read",
              { path: join(dirname(skillPath), "support.txt") },
              { id: "support" },
            ),
          ],
          { stopReason: "toolUse" },
        );
      },
      (context) => {
        assert.ok(
          JSON.stringify(context.messages).includes("NATIVE_SKILL_RESULT"),
        );
        return text();
      },
    ],
  );
  assert.deepEqual(
    atifResults(snapshots).map((result) => result.source_call_id),
    ["skill", "support"],
  );
  assert.equal(meta(latest(snapshots).agent).skills?.[0]?.name, "greeting");
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("commissioned skills without a native file reader are refused", async () => {
  const { snapshots, faux } = await scripted(
    received({
      agents: { "avp-pi": { enabled_tools: [] } },
      skills: [
        {
          name: "greeting",
          files: {
            "SKILL.md":
              "---\nname: greeting\ndescription: Greeting\n---\nGREETING",
          },
        },
      ],
    }),
    [],
  );
  assert.equal(
    meta(atifErrors(snapshots)[0]!).error_code,
    "invalid_commission",
  );
  assert.equal(faux.state.callCount, 0);
});

/** Native Pi sessions and MCP clients produce validated SDK Trajectories. */
import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import {
  parseTrajectoryEvent,
  type Event,
  type JsonValue,
} from "@agent-voyager-project/sdk/trajectory";
import {
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
type DataByType = { [E in Event as E["type"]]: E["data"] };
function data<K extends keyof DataByType>(
  events: Event[],
  kind: K,
): DataByType[K][] {
  return events
    .filter((e) => e.type === kind)
    .map((e) => e.data) as DataByType[K][];
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
  const events: Event[] = [];
  const before = process.cwd();
  process.chdir(cwd);
  try {
    await run(
      commission,
      async (event) => {
        if (options.slowSink) await delay(5);
        const parsed = parseTrajectoryEvent(event);
        assert.ok(parsed);
        events.push(parsed);
      },
      options.signal ?? new AbortController().signal,
      { modelRuntime: models },
    );
    return { events, cwd, faux };
  } finally {
    process.chdir(before);
    rmSync(cwd, { force: true, recursive: true });
  }
}
const text = (value = "DONE") => fauxAssistantMessage([fauxText(value)]);

test("native responses retain reasoning, skills, replacement instructions, and per-response usage", async () => {
  let system: string | undefined;
  const { events } = await scripted(
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
          .map((m) => m.content)
          .join("\n\n");
        return fauxAssistantMessage([
          fauxThinking("THOUGHT"),
          fauxText("DONE"),
        ]);
      },
    ],
  );
  assert.deepEqual(
    events.map((e) => e.type),
    [
      "run_requested",
      "agent_described",
      "agent_started",
      "assistant_message",
      "agent_stopped",
    ],
  );
  assert.ok(system?.startsWith("SYSTEM\n\n## Skill: greeting"));
  assert.ok(system?.includes("SUPPORT"));
  assert.equal(data(events, "agent_started")[0]!.system_prompt, system);
  const response = data(events, "assistant_message")[0]!;
  assert.equal(response.content[0]!.type, "thinking");
  assert.ok(
    response.usage.input_tokens > 0 && response.usage.output_tokens > 0,
  );
  assert.equal(data(events, "agent_stopped")[0]!.output, "DONE");
});

test("native filesystem and bash tools complete with ordered asynchronous sink writes", async () => {
  const { events } = await scripted(
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
  assert.equal(data(events, "assistant_message").length, 3);
  const returns = data(events, "tool_returned");
  assert.deepEqual(
    returns.map((e) => e.tool_call_id),
    ["write", "read"],
  );
  assert.match(JSON.stringify(returns[1]!.tool_result.content), /BOUNDARY/);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
  for (const result of returns)
    assert.ok(
      events.findIndex(
        (e) =>
          e.type === "tool_invoked" &&
          e.data.tool_call_id === result.tool_call_id,
      ) <
        events.findIndex(
          (e) =>
            e.type === "tool_returned" &&
            e.data.tool_call_id === result.tool_call_id,
        ),
    );
});

test("disabled built-ins are absent from the model and refused if called", async () => {
  const { events } = await scripted(
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
  assert.equal(data(events, "agent_started")[0]!.tools, undefined);
  assert.equal(data(events, "tool_returned")[0]!.tool_result.is_error, true);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
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
    const { events } = await scripted(
      received({
        agents: { "avp-pi": { enabled_tools: [] } },
        mcp_servers: [
          { type: "stdio", id: "fixture", command: ["python3", fixture] },
        ],
      }),
      [fauxAssistantMessage(calls, { stopReason: "toolUse" }), text()],
    );
    const invoked = data(events, "tool_invoked");
    const returned = data(events, "tool_returned");
    assert.equal(invoked.length, calls.length);
    assert.equal(returned.length, calls.length);
    assert.ok(invoked.every((e) => e.mcp_server_id === "fixture"));
    assert.match(
      JSON.stringify(
        returned.find((e) => e.tool_call_id === "echo")!.tool_result.content,
      ),
      /BOUNDARY/,
    );
    if (mode === "errors") {
      assert.equal(
        returned.find((e) => e.tool_call_id === "result")!.tool_result.is_error,
        true,
      );
      assert.equal(
        returned.find((e) => e.tool_call_id === "protocol")!.tool_result
          .is_error,
        true,
      );
    }
    assert.equal(data(events, "assistant_message").length, 2);
    assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
  });

for (const fields of [
  { agents: { other: {} } },
  { agents: { "avp-pi": { enabled_tools: ["missing"] } } },
  { output_schema: { type: "object" } },
  { model: { provider: "missing", id: "missing" } },
])
  test(`unusable Commission stops before any model call: ${JSON.stringify(fields)}`, async () => {
    const { events, faux } = await scripted(received(fields), []);
    assert.deepEqual(
      events.map((e) => e.type),
      ["run_requested", "agent_described", "error_occurred"],
    );
    assert.equal(
      data(events, "error_occurred")[0]!.error_code,
      "invalid_commission",
    );
    assert.equal(faux.state.callCount, 0);
  });

test("missing environment credentials stop as auth_error", async () => {
  delete process.env.MISSING_AVP_PI_KEY;
  const { events } = await scripted(
    received({
      model: {
        provider: "anthropic",
        id: MODEL,
        credential: { env: "MISSING_AVP_PI_KEY" },
      },
    }),
    [],
  );
  assert.equal(data(events, "error_occurred")[0]!.error_code, "auth_error");
});

test("unreachable MCP server stops before model execution", async () => {
  const { events, faux } = await scripted(
    received({
      mcp_servers: [
        { type: "stdio", id: "bad", command: ["/nonexistent/mcp"] },
      ],
    }),
    [],
  );
  assert.equal(
    data(events, "error_occurred")[0]!.error_code,
    "mcp_connect_failed",
  );
  assert.equal(faux.state.callCount, 0);
});

test("provider errors are terminal errors rather than synthetic model responses", async () => {
  const { events } = await scripted(received(), [
    fauxAssistantMessage([], {
      stopReason: "error",
      errorMessage: "401 authentication failed",
    }),
  ]);
  assert.equal(data(events, "assistant_message").length, 0);
  assert.equal(data(events, "error_occurred")[0]!.error_code, "auth_error");
  assert.equal(data(events, "agent_stopped")[0]!.reason, "error");
});

test("cancelling a native streamed response closes the run as interrupted", async () => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 150);
  try {
    const { events } = await scripted(
      received(),
      [text("A long streamed response to interrupt")],
      { signal: controller.signal, tokensPerSecond: 2 },
    );
    assert.equal(data(events, "agent_stopped")[0]!.reason, "interrupted");
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
    const { events } = await scripted(
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
    const results = data(events, "tool_returned");
    assert.equal(results.length, 2);
    assert.ok(
      results.every(
        (result) =>
          result.tool_result.structured_content?.value === "fixture-env-value",
      ),
    );
    assert.deepEqual(
      new Set(data(events, "tool_invoked").map((call) => call.mcp_server_id)),
      new Set(["same-name", "same_name"]),
    );
    assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
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
  const events: Event[] = [];
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
        events.push(event);
      },
      new AbortController().signal,
    );
    assert.equal(key, "avp-proxy-stand-in");
    const response = data(events, "assistant_message")[0]!;
    assert.equal(response.usage.input_tokens, 1000);
    assert.equal(response.usage.output_tokens, 50);
    assert.equal(response.usage.cache_read_input_tokens, 300);
    assert.equal(response.usage.cache_creation_input_tokens, 100);
    assert.equal(response.response_model, "claude-haiku-4-5-20251001");
    assert.deepEqual(response.finish_reasons, ["end_turn"]);
    assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});

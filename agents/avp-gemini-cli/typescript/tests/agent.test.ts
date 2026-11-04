/** Real Gemini sessions, schedulers, tools, and MCP clients cross the Recorder. */
import { strict as assert } from "node:assert";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
  mkdirSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, type TestContext } from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import {
  coreEvents,
  CoreEvent,
  FakeContentGenerator,
  type ContentGenerator,
} from "@google/gemini-cli-core";
import {
  parseTrajectoryEvent,
  type Event,
  type JsonValue,
} from "@agent-voyager-project/sdk/trajectory";
import { run } from "../src/agent.js";
import { describe } from "../src/descriptor.js";
const MODEL = "gemini-2.5-flash";
const packageRoot = fileURLToPath(new URL("../../", import.meta.url));
const fixture = fileURLToPath(
  new URL("../../../../../testing/mcp/avp_test_mcp.py", import.meta.url),
);
const received = (extra: Record<string, unknown> = {}): JsonValue =>
  ({
    avp_version: "0.1",
    run_id: "gemini-native-test",
    model: {
      provider: "google",
      id: MODEL,
      credential: { proxy: "test-standin" },
    },
    prompt: "Do the requested task.",
    ...extra,
  }) as JsonValue;
function response(
  parts: Record<string, unknown>[],
  usage: Record<string, unknown> = {},
) {
  return [
    {
      candidates: [
        { content: { role: "model", parts }, finishReason: "STOP", index: 0 },
      ],
      usageMetadata: {
        promptTokenCount: 120,
        candidatesTokenCount: 8,
        totalTokenCount: 128,
        ...usage,
      },
      modelVersion: MODEL,
    },
  ];
}
const call = (id: string, name: string, args: Record<string, unknown>) => ({
  functionCall: { id, name, args },
});
const fake = (responses: ReturnType<typeof response>[]): ContentGenerator =>
  new FakeContentGenerator(
    responses.map((r) => ({
      method: "generateContentStream",
      response: r,
    })) as never,
  );
type DataByType = { [E in Event as E["type"]]: E["data"] };
function data<K extends keyof DataByType>(
  events: Event[],
  type: K,
): DataByType[K][] {
  return events
    .filter((event) => event.type === type)
    .map((event) => event.data) as DataByType[K][];
}
async function drive(
  t: TestContext,
  commission: JsonValue,
  generator?: ContentGenerator,
  options: { signal?: AbortSignal; setup?: (cwd: string) => void } = {},
) {
  const cwd = mkdtempSync(join(tmpdir(), "avp-gemini-test-"));
  t.after(() => rmSync(cwd, { recursive: true, force: true }));
  options.setup?.(cwd);
  const previous = process.cwd();
  const events: Event[] = [];
  const listeners = coreEvents.listenerCount(CoreEvent.McpProgress);
  process.chdir(cwd);
  try {
    await run(
      commission,
      async (event) => {
        await delay(1);
        events.push(parseTrajectoryEvent(JSON.parse(JSON.stringify(event)))!);
      },
      { contentGenerator: generator, signal: options.signal },
    );
  } finally {
    process.chdir(previous);
  }
  assert.equal(
    coreEvents.listenerCount(CoreEvent.McpProgress),
    listeners,
    "native scheduler listeners are disposed",
  );
  return { events, cwd };
}

test("installed CLI ping stays independent of the native runtime", () => {
  const main = fileURLToPath(new URL("../src/main.js", import.meta.url));
  assert.deepEqual(
    JSON.parse(
      execFileSync(process.execPath, [main, "ping"], { encoding: "utf8" }),
    ),
    { type: "pong", avp_version: "0.1" },
  );
});

test("Descriptor reads built-in catalogs and explicitly declares subagent tools", async () => {
  const descriptor = await describe();
  assert.equal(descriptor.agent_name, "avp-gemini-cli");
  assert.ok(descriptor.tools?.some((tool) => tool.name === "write_file"));
  assert.ok(!descriptor.tools?.some((tool) => tool.name === "ask_user"));
  assert.deepEqual(descriptor.subagents?.map((a) => a.name).sort(), [
    "cli_help",
    "codebase_investigator",
    "generalist",
  ]);
  for (const agent of descriptor.subagents ?? [])
    assert.ok(agent.tools?.some((tool) => tool.name === "complete_task"));
  assert.ok(descriptor.skills?.some((skill) => skill.name === "skill-creator"));
});

test("native filesystem loop keeps response usage, thoughts, tool IDs, and async event order", async (t) => {
  const { events, cwd } = await drive(
    t,
    received(),
    fake([
      response(
        [
          { text: "Checking.", thought: true },
          call("w1", "write_file", { file_path: "out.txt", content: "OK" }),
        ],
        {
          cachedContentTokenCount: 100,
          thoughtsTokenCount: 30,
          toolUsePromptTokenCount: 5,
        },
      ),
      response([{ text: "DONE" }], { promptTokenCount: 200 }),
    ]),
  );
  assert.equal(readFileSync(join(cwd, "out.txt"), "utf8"), "OK");
  assert.deepEqual(
    events.map((event) => event.type),
    [
      "run_requested",
      "agent_described",
      "agent_started",
      "assistant_message",
      "tool_invoked",
      "tool_returned",
      "assistant_message",
      "agent_stopped",
    ],
  );
  const first = data(events, "assistant_message")[0]!;
  assert.equal(first.usage.input_tokens, 125);
  assert.equal(first.usage.output_tokens, 38);
  assert.equal(first.usage.cache_read_input_tokens, 100);
  assert.equal(first.usage.reasoning_output_tokens, 30);
  assert.equal(first.usage.cost_source, "computed");
  assert.equal(first.response_model, MODEL);
  const invoked = data(events, "tool_invoked")[0]!;
  assert.equal(
    data(events, "tool_returned")[0]!.tool_call_id,
    invoked.tool_call_id,
  );
  assert.equal(data(events, "agent_stopped")[0]!.output, "DONE");
});

test("native tool allowlists and custom system prompt replace the defaults", async (t) => {
  const generator = fake([response([{ text: "OK" }])]);
  let system = "";
  const stream = generator.generateContentStream.bind(generator);
  generator.generateContentStream = async (...args) => {
    system = JSON.stringify(args[0].config?.systemInstruction);
    return stream(...args);
  };
  const { events } = await drive(
    t,
    received({
      system_prompt: "ONLY_SYSTEM",
      agents: {
        "avp-gemini-cli": {
          enabled_tools: [],
          enabled_skills: [],
          enabled_subagents: [],
        },
      },
    }),
    generator,
  );
  const started = data(events, "agent_started")[0]!;
  assert.deepEqual(started.tools, []);
  assert.deepEqual(started.skills, []);
  assert.deepEqual(started.subagents, []);
  assert.ok(system.includes("ONLY_SYSTEM"));
  assert.ok(!system.includes("You are an interactive"));
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("invalid Commission and unsupported structured output refuse before native generation", async (t) => {
  for (const c of [
    received({ output_schema: { type: "object" } }),
    received({
      agents: { "avp-gemini-cli": { enabled_tools: ["imaginary"] } },
    }),
  ]) {
    const { events } = await drive(t, c, fake([]));
    assert.equal(
      data(events, "error_occurred")[0]!.error_code,
      "invalid_commission",
    );
    assert.equal(data(events, "agent_started").length, 0);
  }
});

test("native skill activation loads commissioned files and does not discover workspace skills", async (t) => {
  const { events } = await drive(
    t,
    received({
      skills: [
        {
          name: "migration-check",
          files: {
            "SKILL.md":
              "---\nname: migration-check\ndescription: Migration check\n---\nNATIVE_SKILL_BODY",
            "support.txt": "SUPPORT",
          },
        },
      ],
    }),
    fake([
      response([call("skill", "activate_skill", { name: "migration-check" })]),
      response([{ text: "DONE" }]),
    ]),
    {
      setup(cwd) {
        const dir = join(cwd, ".gemini", "skills", "ambient");
        mkdirSync(dir, { recursive: true });
        writeFileSync(
          join(dir, "SKILL.md"),
          "---\nname: ambient\ndescription: Ambient\n---\nAMBIENT",
        );
      },
    },
  );
  const started = data(events, "agent_started")[0]!;
  assert.ok(started.skills?.some((skill) => skill.name === "migration-check"));
  assert.ok(!started.skills?.some((skill) => skill.name === "ambient"));
  assert.ok(!started.system_prompt?.includes("NATIVE_SKILL_BODY"));
  assert.match(
    JSON.stringify(data(events, "tool_returned")),
    /NATIVE_SKILL_BODY/,
  );
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("native MCP connection and parallel tools preserve ownership and both error forms", async (t) => {
  const { events } = await drive(
    t,
    received({
      mcp_servers: [
        { id: "avptest", type: "stdio", command: ["python3", fixture] },
      ],
      agents: { "avp-gemini-cli": { enabled_tools: [] } },
    }),
    fake([
      response([
        call("m1", "mcp_avptest_Avptest_Echo", { text: "MCP_OK" }),
        call("m2", "mcp_avptest_Avptest_Fail", {
          message: "MCP_FAILURE",
          mode: "result",
        }),
        call("m3", "mcp_avptest_Avptest_Fail", {
          message: "MCP_PROTOCOL",
          mode: "protocol",
        }),
      ]),
      response([{ text: "DONE" }]),
    ]),
  );
  const started = data(events, "agent_started")[0]!;
  assert.equal(started.mcp_servers?.[0]?.status, "connected");
  assert.equal(
    started.tools?.find((tool) => tool.name.endsWith("Avptest_Echo"))
      ?.mcp_server_id,
    "avptest",
  );
  const returned = data(events, "tool_returned");
  assert.equal(returned.length, 3);
  assert.equal(returned.filter((r) => r.tool_result.is_error).length, 2);
  assert.match(JSON.stringify(returned), /MCP_OK/);
  assert.equal(new Set(returned.map((r) => r.tool_call_id)).size, 3);
});

test("native subagent model calls roll up exactly once on their invocation", async (t) => {
  const { events } = await drive(
    t,
    received(),
    fake([
      response([
        call("agent1", "invoke_agent", {
          agent_name: "codebase_investigator",
          prompt: "Inspect this workspace.",
        }),
      ]),
      response([
        call("done", "complete_task", {
          report: {
            SummaryOfFindings: "CHILD_DONE",
            ExplorationTrace: [],
            RelevantLocations: [],
          },
        }),
      ]),
      response([{ text: "DONE" }]),
    ]),
  );
  assert.equal(data(events, "subagent_invoked").length, 1);
  const returned = data(events, "subagent_returned")[0]!;
  assert.equal(returned.subagent_usage?.responses, 1);
  assert.equal(returned.subagent_usage?.input_tokens, 120);
  assert.equal(returned.subagent_usage?.output_tokens, 8);
  assert.equal(data(events, "assistant_message").length, 2);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("missing model environment credentials refuse before a model request", async (t) => {
  const { events } = await drive(
    t,
    received({
      model: {
        provider: "google",
        id: MODEL,
        credential: { env: "AVP_MISSING_GEMINI_KEY" },
      },
    }),
    fake([]),
  );
  assert.equal(data(events, "error_occurred")[0]!.error_code, "auth_error");
  assert.equal(data(events, "agent_started").length, 0);
});

test("failed MCP discovery stops before a model call", async (t) => {
  const { events } = await drive(
    t,
    received({
      mcp_servers: [
        { id: "missing", type: "stdio", command: ["avp-missing-executable"] },
      ],
    }),
    fake([]),
  );
  assert.equal(
    data(events, "error_occurred")[0]!.error_code,
    "mcp_connect_failed",
  );
  assert.equal(data(events, "assistant_message").length, 0);
});

test("missing native response usage fails visibly", async (t) => {
  const chunk = response([{ text: "UNACCOUNTED" }])[0]!;
  const { usageMetadata: _, ...withoutUsage } = chunk;
  const generator = new FakeContentGenerator([
    { method: "generateContentStream", response: [withoutUsage] },
  ] as never);
  const { events } = await drive(t, received(), generator);
  assert.equal(data(events, "assistant_message").length, 0);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "error");
  assert.match(
    JSON.stringify(data(events, "error_occurred")),
    /usage metadata/,
  );
});

test("native cancellation closes the started run as interrupted", async (t) => {
  const controller = new AbortController();
  controller.abort();
  const { events } = await drive(t, received(), fake([]), {
    signal: controller.signal,
  });
  assert.equal(data(events, "agent_stopped")[0]!.reason, "interrupted");
  assert.equal(data(events, "assistant_message").length, 0);
});

test("unknown subagent requests remain native tool errors without fabricated frames", async (t) => {
  const { events } = await drive(
    t,
    received(),
    fake([
      response([
        call("unknown", "invoke_agent", {
          agent_name: "imaginary",
          prompt: "work",
        }),
      ]),
      response([{ text: "DONE" }]),
    ]),
  );
  assert.equal(data(events, "subagent_invoked").length, 0);
  assert.equal(data(events, "tool_returned")[0]!.tool_result.is_error, true);
});

test("native Google HTTP client sends the proxy stand-in and records served model and cache usage", async (t) => {
  const requests: { path: string; key: string | undefined; body: string }[] =
    [];
  const server = createServer(async (request, response_) => {
    let body = "";
    for await (const chunk of request) body += chunk;
    requests.push({
      path: request.url!,
      key: request.headers["x-goog-api-key"] as string | undefined,
      body,
    });
    response_.writeHead(200, { "content-type": "text/event-stream" });
    response_.end(
      `data: ${JSON.stringify({ ...response([{ text: "HTTP_OK" }], { cachedContentTokenCount: 80, thoughtsTokenCount: 3 })[0], modelVersion: "gemini-2.5-flash-001" })}\n\n`,
    );
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(
    () =>
      new Promise<void>((resolve, reject) => {
        server.closeAllConnections();
        server.close((error) => (error ? reject(error) : resolve()));
      }),
  );
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const { events } = await drive(
    t,
    received({
      model: {
        provider: "google",
        id: MODEL,
        base_url: `http://127.0.0.1:${address.port}`,
        credential: { proxy: "standin-only" },
      },
      agents: {
        "avp-gemini-cli": {
          enabled_tools: [],
          enabled_skills: [],
          enabled_subagents: [],
        },
      },
    }),
  );
  assert.equal(
    requests.length,
    1,
    JSON.stringify(data(events, "error_occurred")),
  );
  assert.equal(requests[0]!.key, "standin-only");
  assert.match(requests[0]!.path, /gemini-2.5-flash:streamGenerateContent/);
  const message = data(events, "assistant_message")[0]!;
  assert.equal(message.response_model, "gemini-2.5-flash-001");
  assert.equal(message.usage.input_tokens, 120);
  assert.equal(message.usage.output_tokens, 11);
  assert.equal(message.usage.cache_read_input_tokens, 80);
  assert.equal(data(events, "agent_stopped")[0]!.output, "HTTP_OK");
});

test("parallel native subagents keep usage attached to their own invocation", async (t) => {
  const { events } = await drive(
    t,
    received(),
    fake([
      response([
        call("child1", "invoke_agent", {
          agent_name: "codebase_investigator",
          prompt: "First inspection",
        }),
        call("child2", "invoke_agent", {
          agent_name: "codebase_investigator",
          prompt: "Second inspection",
        }),
      ]),
      response(
        [
          call("complete1", "complete_task", {
            report: {
              SummaryOfFindings: "FIRST",
              ExplorationTrace: [],
              RelevantLocations: [],
            },
          }),
        ],
        { promptTokenCount: 150 },
      ),
      response(
        [
          call("complete2", "complete_task", {
            report: {
              SummaryOfFindings: "SECOND",
              ExplorationTrace: [],
              RelevantLocations: [],
            },
          }),
        ],
        { promptTokenCount: 250 },
      ),
      response([{ text: "DONE" }]),
    ]),
  );
  const children = data(events, "subagent_returned");
  assert.equal(children.length, 2);
  assert.deepEqual(
    children
      .map((child) => child.subagent_usage?.input_tokens)
      .sort((a, b) => a! - b!),
    [150, 250],
  );
  assert.ok(
    children.every(
      (child) =>
        child.subagent_usage?.responses === 1 &&
        child.subagent_reason === "converged",
    ),
  );
  assert.equal(data(events, "assistant_message").length, 2);
  const generalist = data(events, "agent_started")[0]!.subagents?.find(
    (agent) => agent.name === "generalist",
  );
  assert.ok(
    !generalist?.tools?.some(
      (tool) => tool.name === "invoke_agent" || tool.name === "update_topic",
    ),
  );
});

test("native child failures stay failures even when the parent recovers", async (t) => {
  const generator = fake([
    response([
      call("child", "invoke_agent", {
        agent_name: "codebase_investigator",
        prompt: "Inspect",
      }),
    ]),
    response([{ text: "RECOVERED" }]),
  ]);
  const stream = generator.generateContentStream.bind(generator);
  generator.generateContentStream = async (...args) => {
    if (args[2] === "subagent") throw new Error("invalid API key (401)");
    return stream(...args);
  };
  const { events } = await drive(t, received(), generator);
  const child = data(events, "subagent_returned")[0]!;
  assert.equal(child.subagent_reason, "error");
  assert.equal(child.subagent_usage, undefined);
  assert.equal(data(events, "tool_returned")[0]!.tool_result.is_error, true);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("native shell execution uses the launcher's workspace", async (t) => {
  const { events, cwd } = await drive(
    t,
    received(),
    fake([
      response([
        call("shell", "run_shell_command", {
          command:
            "printf NATIVE_SHELL > native-shell.txt; cat native-shell.txt",
        }),
      ]),
      response([{ text: "DONE" }]),
    ]),
  );
  assert.equal(
    readFileSync(join(cwd, "native-shell.txt"), "utf8"),
    "NATIVE_SHELL",
  );
  const result = data(events, "tool_returned")[0]!.tool_result;
  assert.equal(result.is_error, false, JSON.stringify(result));
  assert.match(JSON.stringify(result.content), /NATIVE_SHELL/);
});

test("an explicit empty system prompt keeps the native base empty", async (t) => {
  const { events } = await drive(
    t,
    received({
      system_prompt: "",
      agents: {
        "avp-gemini-cli": {
          enabled_tools: [],
          enabled_skills: [],
          enabled_subagents: [],
        },
      },
    }),
    fake([response([{ text: "OK" }])]),
  );
  assert.equal(data(events, "agent_started")[0]!.system_prompt, "");
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("native main-model promotion is refused before any provider request", async (t) => {
  const generator = fake([]);
  let calls = 0;
  const stream = generator.generateContentStream.bind(generator);
  generator.generateContentStream = async (...args) => {
    calls++;
    return stream(...args);
  };
  const { events } = await drive(
    t,
    received({
      model: {
        provider: "google",
        id: "gemini-3.1-flash-lite",
        credential: { proxy: "test-standin" },
      },
    }),
    generator,
  );
  assert.equal(calls, 0);
  assert.equal(data(events, "assistant_message").length, 0);
  assert.match(
    data(events, "error_occurred")[0]!.error_message,
    /changed the commissioned model to gemini-3.5-flash-lite/,
  );
  assert.equal(data(events, "agent_stopped")[0]!.reason, "error");
});

/** Drive the pinned native server and validate its Recorder Trajectory. */
import { strict as assert } from "node:assert";
import { randomUUID } from "node:crypto";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
  mkdirSync,
  writeFileSync,
  renameSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, type TestContext } from "node:test";
import { execFileSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import {
  parseTrajectoryEvent,
  type Event,
  type JsonValue,
} from "@agent-voyager-project/sdk/trajectory";
import { run } from "../src/agent.js";
import { describe } from "../src/descriptor.js";
import { ScriptedModel, type Step } from "./scripted.js";
const MODEL = "gpt-4.1";
const fixture = fileURLToPath(
  new URL("../../../../../testing/mcp/avp_test_mcp.py", import.meta.url),
);
type DataByType = { [E in Event as E["type"]]: E["data"] };
function data<K extends keyof DataByType>(
  events: Event[],
  type: K,
): DataByType[K][] {
  return events
    .filter((e) => e.type === type)
    .map((e) => e.data) as DataByType[K][];
}
async function drive(
  t: TestContext,
  extra: Record<string, unknown>,
  steps: Step[] | ((cwd: string) => Step[]),
  options: {
    signal?: AbortSignal;
    setup?: (cwd: string) => void;
    abortAfterRequest?: AbortController;
    env?: Record<string, string | undefined>;
  } = {},
) {
  const model = await ScriptedModel.start();
  t.after(() => model.close());
  const cwd = mkdtempSync(join(tmpdir(), "avp-opencode-test-"));
  t.after(() => rmSync(cwd, { recursive: true, force: true }));
  options.setup?.(cwd);
  model.script(typeof steps === "function" ? steps(cwd) : steps);
  const received = {
    avp_version: "0.1",
    run_id: "opencode-native-test",
    prompt: "Do the requested task.",
    ...extra,
    model: {
      provider: "openai",
      id: MODEL,
      base_url: model.baseUrl,
      credential: { proxy: "test-standin" },
      ...((extra.model as Record<string, unknown>) ?? {}),
    },
  } as JsonValue;
  const events: Event[] = [];
  let requestsAtStart: number | undefined;
  const previous = process.cwd();
  process.chdir(cwd);
  try {
    const work = run(
      received,
      async (event) => {
        await delay(1);
        if (event.type === "agent_started")
          requestsAtStart = model.requests.length;
        events.push(parseTrajectoryEvent(JSON.parse(JSON.stringify(event)))!);
      },
      { signal: options.signal, env: options.env },
    );
    if (options.abortAfterRequest) {
      while (!model.requests.length) await delay(5);
      await delay(250);
      options.abortAfterRequest.abort();
    }
    await work;
  } finally {
    process.chdir(previous);
  }
  if (process.env.AVP_ATIF_CAPTURE) {
    writeFileSync(
      join(process.env.AVP_ATIF_CAPTURE, `${randomUUID()}.ndjson`),
      events.map((event) => JSON.stringify(event)).join("\n") + "\n",
    );
  }
  return {
    events,
    cwd,
    requests: model.requests,
    headers: model.requestHeaders,
    requestsAtStart,
  };
}

function system(request: Record<string, any>): string {
  return (
    request.instructions ??
    (request.input ?? [])
      .filter((message: { role: string }) =>
        ["system", "developer"].includes(message.role),
      )
      .map((message: { content: string }) => message.content)
      .join("\n")
  );
}

test("CLI ping does not load the native runtime", () => {
  assert.deepEqual(
    JSON.parse(
      execFileSync(
        process.execPath,
        [fileURLToPath(new URL("../src/main.js", import.meta.url)), "ping"],
        { encoding: "utf8" },
      ),
    ),
    { type: "pong", avp_version: "0.1" },
  );
});

test("native Descriptor includes built-in catalogs and explicit child items", async () => {
  const d = await describe();
  assert.equal(d.agent_name, "avp-opencode");
  assert.ok(d.tools?.some((t) => t.name === "write"));
  assert.ok(d.tools?.some((t) => t.name === "apply_patch"));
  assert.ok(!d.tools?.some((t) => t.name === "invalid"));
  assert.deepEqual(d.subagents?.map((a) => a.name).sort(), [
    "explore",
    "general",
  ]);
  assert.ok(d.subagents?.every((a) => a.tools?.length));
  assert.ok(d.skills?.some((s) => s.name === "customize-opencode"));
  assert.ok(d.supported_models?.some((m) => m.provider === "anthropic"));
});

test("native tool loop preserves response deltas, reported cost, and awaited sink order", async (t) => {
  const { events, cwd, requests } = await drive(t, {}, (cwd) => [
    {
      call: {
        id: "write1",
        name: "write",
        args: { filePath: join(cwd, "answer.txt"), content: "OK" },
      },
    },
    { text: "DONE", usage: { input: 200, cached: 50, output: 40 } },
  ]);
  assert.equal(readFileSync(join(cwd, "answer.txt"), "utf8"), "OK");
  assert.deepEqual(
    events.map((e) => e.type),
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
  const responses = data(events, "assistant_message");
  assert.equal(responses.length, 2);
  assert.deepEqual(
    responses.map((r) => r.usage.input_tokens),
    [120, 200],
  );
  assert.deepEqual(
    responses.map((r) => r.usage.output_tokens),
    [30, 40],
  );
  assert.equal(responses[0]!.usage.cache_read_input_tokens, 20);
  assert.ok(
    responses.every(
      (r) => r.usage.cost_source === "reported" && r.usage.cost_usd > 0,
    ),
  );
  assert.equal(data(events, "tool_returned")[0]!.tool_call_id, "write1");
  assert.equal(data(events, "tool_returned")[0]!.tool_result.is_error, false);
  assert.equal(data(events, "agent_stopped")[0]!.output, "DONE");
  assert.equal(requests.length, 2);
});

test("native allowlists expose no tools or child agents when disabled", async (t) => {
  const { events, requests } = await drive(
    t,
    {
      agents: {
        "avp-opencode": {
          enabled_tools: [],
          enabled_subagents: [],
          enabled_skills: [],
        },
      },
    },
    [{ text: "OK" }],
  );
  const started = data(events, "agent_started")[0]!;
  assert.deepEqual(started.tools, []);
  assert.deepEqual(started.subagents, []);
  assert.deepEqual(started.skills, []);
  assert.ok(!requests[0]!.tools?.length);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("the full assembled default prompt is recorded before the model request", async (t) => {
  const { events, requests, cwd, requestsAtStart } = await drive(t, {}, [
    { text: "OK" },
  ]);
  const actual = system(requests[0]!);
  assert.match(actual, /You are opencode/);
  assert.ok(actual.includes(cwd));
  assert.match(actual, /<env>/);
  assert.equal(data(events, "agent_started")[0]!.system_prompt, actual);
  assert.equal(requestsAtStart, 0);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("explicit instructions replace the entire native prompt on every parent response", async (t) => {
  const { events, requests, requestsAtStart } = await drive(
    t,
    {
      system_prompt: "ONLY_COMMISSION_INSTRUCTIONS",
      skills: [
        {
          name: "prompt-check",
          files: {
            "SKILL.md":
              "---\nname: prompt-check\ndescription: PROMPT_CHECK_SKILL\n---\nSKILL_BODY",
          },
        },
      ],
    },
    (cwd) => [
      {
        call: {
          id: "prompt-write",
          name: "write",
          args: { filePath: join(cwd, "prompt.txt"), content: "OK" },
        },
      },
      { text: "OK" },
    ],
  );
  assert.equal(requests.length, 2);
  assert.deepEqual(requests.map(system), [
    "ONLY_COMMISSION_INSTRUCTIONS",
    "ONLY_COMMISSION_INSTRUCTIONS",
  ]);
  assert.equal(
    data(events, "agent_started")[0]!.system_prompt,
    "ONLY_COMMISSION_INSTRUCTIONS",
  );
  assert.equal(requestsAtStart, 0);
  assert.equal(data(events, "tool_returned")[0]!.tool_result.is_error, false);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("an empty system-prompt override sends no native system instructions", async (t) => {
  const { events, requests, requestsAtStart } = await drive(
    t,
    { system_prompt: "" },
    [{ text: "OK" }],
  );
  assert.equal(requests.length, 1);
  assert.equal(system(requests[0]!), "");
  assert.equal(data(events, "agent_started")[0]!.system_prompt, "");
  assert.equal(requestsAtStart, 0);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("a missing bundled prompt hook refuses the run before a model request", async (t) => {
  const hook = fileURLToPath(
    new URL("../src/prompt-plugin.js", import.meta.url),
  );
  renameSync(hook, `${hook}.disabled`);
  try {
    const { events, requests } = await drive(
      t,
      { system_prompt: "ONLY_COMMISSION" },
      [],
    );
    assert.equal(requests.length, 0);
    assert.equal(data(events, "agent_started").length, 0);
    assert.match(
      data(events, "error_occurred")[0]!.error_message,
      /did not load.*system-prompt hook/,
    );
  } finally {
    renameSync(`${hook}.disabled`, hook);
  }
});

test("native skill activation uses commissioned SKILL.md and hides ambient skills", async (t) => {
  const { events } = await drive(
    t,
    {
      skills: [
        {
          name: "migration-check",
          files: {
            "SKILL.md":
              "---\nname: migration-check\ndescription: Migration verification\n---\nNATIVE_SKILL_BODY",
            "support.txt": "SUPPORT",
          },
        },
      ],
    },
    [
      {
        call: {
          id: "skill1",
          name: "skill",
          args: { name: "migration-check" },
        },
      },
      { text: "DONE" },
    ],
    {
      setup(cwd) {
        const dir = join(cwd, ".opencode", "skills", "ambient");
        mkdirSync(dir, { recursive: true });
        writeFileSync(
          join(dir, "SKILL.md"),
          "---\nname: ambient\ndescription: Ambient\n---\nAMBIENT",
        );
      },
    },
  );
  const skills = data(events, "agent_started")[0]!.skills ?? [];
  assert.ok(skills.some((s) => s.name === "migration-check"));
  assert.ok(!skills.some((s) => s.name === "ambient"));
  assert.match(
    JSON.stringify(data(events, "tool_returned")),
    /NATIVE_SKILL_BODY/,
  );
});

test("native MCP tools retain server ownership, parallel call IDs, and both error forms", async (t) => {
  const { events } = await drive(
    t,
    {
      mcp_servers: [
        { id: "avptest", type: "stdio", command: ["python3", fixture] },
      ],
      agents: { "avp-opencode": { enabled_tools: [] } },
    },
    [
      {
        calls: [
          { id: "one", name: "avptest_Avptest_Echo", args: { text: "MCP_OK" } },
          {
            id: "two",
            name: "avptest_Avptest_Fail",
            args: { message: "MCP_RESULT_FAILURE", mode: "result" },
          },
          {
            id: "three",
            name: "avptest_Avptest_Fail",
            args: { message: "MCP_PROTOCOL_FAILURE", mode: "protocol" },
          },
        ],
      },
      { text: "DONE" },
    ],
  );
  const started = data(events, "agent_started")[0]!;
  assert.equal(started.mcp_servers?.[0]?.status, "connected");
  assert.equal(
    started.tools?.find((t) => t.name === "avptest_Avptest_Echo")
      ?.mcp_server_id,
    "avptest",
  );
  const returns = data(events, "tool_returned");
  assert.equal(returns.length, 3);
  assert.equal(returns.filter((r) => r.tool_result.is_error).length, 2);
  assert.deepEqual(returns.map((r) => r.tool_call_id).sort(), [
    "one",
    "three",
    "two",
  ]);
  assert.match(JSON.stringify(returns), /MCP_OK/);
});

test("native child responses are scoped individually without rolled-up double counting", async (t) => {
  const { events, requests } = await drive(
    t,
    { system_prompt: "PARENT_ONLY_PROMPT" },
    [
      {
        call: {
          id: "task1",
          name: "task",
          args: {
            subagent_type: "general",
            description: "Inspect",
            prompt: "Reply CHILD_DONE without tools.",
          },
        },
      },
      { text: "CHILD_DONE", usage: { input: 300, cached: 50, output: 20 } },
      { text: "DONE" },
    ],
  );
  const invoked = data(events, "subagent_invoked")[0]!;
  assert.equal(invoked.subagent_name, "general");
  const children = data(events, "assistant_message").filter(
    (r) => r.subagent_invocation_id === invoked.invocation_id,
  );
  assert.equal(children.length, 1);
  assert.equal(children[0]!.usage.input_tokens, 300);
  const returned = data(events, "subagent_returned")[0]!;
  assert.equal(returned.subagent_reason, "converged");
  assert.equal(returned.subagent_usage, undefined);
  assert.match(returned.subagent_result_text, /CHILD_DONE/);
  assert.equal(data(events, "assistant_message").length, 3);
  assert.equal(system(requests[0]!), "PARENT_ONLY_PROMPT");
  assert.equal(system(requests[2]!), "PARENT_ONLY_PROMPT");
  assert.ok(!system(requests[1]!).includes("PARENT_ONLY_PROMPT"));
  assert.match(system(requests[1]!), /<env>/);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("native structured output is returned and its actual tool schema declared", async (t) => {
  const { events } = await drive(
    t,
    {
      output_schema: {
        type: "object",
        properties: { answer: { type: "string" } },
        required: ["answer"],
        additionalProperties: false,
      },
    },
    [
      {
        call: {
          id: "structured",
          name: "StructuredOutput",
          args: { answer: "OK" },
        },
      },
    ],
  );
  assert.ok(
    data(events, "agent_started")[0]!.tools?.some(
      (t) => t.name === "StructuredOutput",
    ),
  );
  assert.deepEqual(data(events, "agent_stopped")[0]!.output, { answer: "OK" });
});

test("invalid Commission and missing environment credentials refuse before a provider request", async (t) => {
  for (const extra of [
    { agents: { "avp-opencode": { enabled_tools: ["imaginary"] } } },
    {
      model: {
        provider: "openai",
        id: MODEL,
        credential: { env: "AVP_MISSING_OPENCODE_TEST_KEY" },
      },
    },
  ]) {
    const { events, requests } = await drive(t, extra, []);
    assert.equal(requests.length, 0);
    assert.equal(data(events, "agent_started").length, 0);
    assert.ok(data(events, "error_occurred").length);
  }
});

test("failed native MCP connection stops before any model request", async (t) => {
  const { events, requests } = await drive(
    t,
    {
      mcp_servers: [
        { type: "stdio", id: "missing", command: ["avp-missing-executable"] },
      ],
    },
    [],
  );
  assert.equal(requests.length, 0);
  assert.equal(
    data(events, "error_occurred")[0]!.error_code,
    "mcp_connect_failed",
  );
});

test("native provider errors are classified without an invented response", async (t) => {
  const { events } = await drive(t, {}, [
    { status: 401, body: { error: { message: "invalid API key" } } },
  ]);
  assert.equal(data(events, "assistant_message").length, 0);
  assert.equal(data(events, "error_occurred")[0]!.error_code, "auth_error");
  assert.equal(data(events, "agent_stopped")[0]!.reason, "error");
});

test("cancellation closes the started run without a provider call", async (t) => {
  const controller = new AbortController();
  controller.abort();
  const { events, requests } = await drive(t, {}, [], {
    signal: controller.signal,
  });
  assert.equal(requests.length, 0);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "interrupted");
});

test("declared child tools match the native request when parent tools are restricted", async (t) => {
  const { events, requests } = await drive(
    t,
    { agents: { "avp-opencode": { enabled_tools: ["task"] } } },
    [
      {
        call: {
          id: "taskonly",
          name: "task",
          args: {
            subagent_type: "general",
            description: "Inspect",
            prompt: "Reply CHILD_DONE.",
          },
        },
      },
      { text: "CHILD_DONE" },
      { text: "DONE" },
    ],
  );
  const child = data(events, "agent_started")[0]!.subagents?.find(
    (a) => a.name === "general",
  );
  const native = (requests[1]!.tools ?? [])
    .map((tool: { name: string }) => tool.name)
    .filter((name: string) => name !== "invalid")
    .sort();
  assert.deepEqual(child?.tools?.map((tool) => tool.name).sort(), native);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("native child tool events stay within their invocation", async (t) => {
  const { events } = await drive(
    t,
    {},
    (cwd) => [
      {
        call: {
          id: "taskread",
          name: "task",
          args: {
            subagent_type: "general",
            description: "Read",
            prompt: "Read the fixture.",
          },
        },
      },
      {
        call: {
          id: "readchild",
          name: "read",
          args: { filePath: join(cwd, "child.txt") },
        },
      },
      { text: "CHILD_DONE" },
      { text: "DONE" },
    ],
    {
      setup(cwd) {
        writeFileSync(join(cwd, "child.txt"), "CHILD_FILE");
      },
    },
  );
  const scope = data(events, "subagent_invoked")[0]!.invocation_id;
  assert.equal(
    data(events, "tool_invoked").find(
      (call) => call.tool_call_id === "readchild",
    )?.subagent_invocation_id,
    scope,
  );
  assert.equal(
    data(events, "tool_returned").find(
      (call) => call.tool_call_id === "readchild",
    )?.subagent_invocation_id,
    scope,
  );
  assert.match(JSON.stringify(data(events, "tool_returned")), /CHILD_FILE/);
  assert.equal(
    data(events, "assistant_message").filter(
      (message) => message.subagent_invocation_id === scope,
    ).length,
    2,
  );
});

test("interruption retains native streamed content and stops the server", async (t) => {
  const controller = new AbortController();
  const { events } = await drive(
    t,
    {},
    [{ text: "PARTIAL ".repeat(100), chunkDelayMs: 100 }],
    { signal: controller.signal, abortAfterRequest: controller },
  );
  const response = data(events, "assistant_message")[0]!;
  assert.ok(
    response.content.some(
      (block) => block.type === "text" && block.text.includes("PARTIAL"),
    ),
  );
  assert.ok(
    response.duration_ms >= 100,
    `partial response duration: ${response.duration_ms}`,
  );
  assert.equal(response.usage.cost_source, "unknown");
  assert.deepEqual(response.finish_reasons, ["aborted"]);
  assert.equal(data(events, "agent_stopped")[0]!.reason, "interrupted");
});

test("project configuration and plugin discovery stay outside the commissioned runtime", async (t) => {
  const { cwd, requests, events } = await drive(
    t,
    { system_prompt: "ONLY_COMMISSION" },
    [{ text: "OK" }],
    {
      setup(cwd) {
        const dir = join(cwd, ".opencode");
        mkdirSync(join(dir, "plugins"), { recursive: true });
        writeFileSync(
          join(dir, "opencode.json"),
          JSON.stringify({ agent: { build: { prompt: "AMBIENT_OVERRIDE" } } }),
        );
        writeFileSync(
          join(dir, "plugins", "ambient.mjs"),
          `import {writeFileSync} from 'node:fs'; export default async()=>{writeFileSync(${JSON.stringify(join(cwd, "unrequested-plugin"))},'EXECUTED');return {};};`,
        );
      },
    },
  );
  assert.equal(
    (await import("node:fs")).existsSync(join(cwd, "unrequested-plugin")),
    false,
  );
  assert.ok(!JSON.stringify(requests).includes("AMBIENT_OVERRIDE"));
  assert.equal(data(events, "agent_stopped")[0]!.reason, "converged");
});

test("native API requests use proxy stand-ins and resolved environment credentials", async (t) => {
  for (const [credential, env, expected] of [
    [{ proxy: "standin-key" }, {}, "standin-key"],
    [
      { env: "AVP_OPENCODE_TEST_KEY" },
      { AVP_OPENCODE_TEST_KEY: "environment-test-key" },
      "environment-test-key",
    ],
  ] as const) {
    const { headers, events } = await drive(
      t,
      { model: { credential } },
      [{ text: "OK" }],
      { env },
    );
    assert.equal(headers[0]!.authorization, `Bearer ${expected}`);
    if ("env" in credential)
      assert.ok(!JSON.stringify(events).includes(expected));
  }
});

test("native reasoning tokens are included once in output usage", async (t) => {
  const { events } = await drive(t, {}, [
    {
      text: "DONE",
      usage: { input: 120, cached: 20, output: 30, reasoning: 10 },
    },
  ]);
  const usage = data(events, "assistant_message")[0]!.usage;
  assert.equal(usage.output_tokens, 30);
  assert.equal(usage.reasoning_output_tokens, 10);
  assert.equal(usage.input_tokens, 120);
});

test("unknown providers are refused before native provider initialization", async (t) => {
  const { events, requests } = await drive(
    t,
    { model: { provider: "avp-unsupported-provider" } },
    [],
  );
  assert.equal(requests.length, 0);
  assert.equal(data(events, "agent_started").length, 0);
  assert.equal(
    data(events, "error_occurred")[0]!.error_code,
    "invalid_commission",
  );
});

test("each declared native child catalog matches the actual model tools", async (t) => {
  for (const subagent_type of ["general", "explore"]) {
    const { events, requests } = await drive(t, {}, [
      {
        call: {
          id: `task-${subagent_type}`,
          name: "task",
          args: {
            subagent_type,
            description: "Inspect",
            prompt: "Reply CHILD_DONE without tools.",
          },
        },
      },
      { text: "CHILD_DONE" },
      { text: "DONE" },
    ]);
    const child = data(events, "agent_started")[0]!.subagents?.find(
      (agent) => agent.name === subagent_type,
    );
    const actual = (requests[1]!.tools ?? [])
      .map((tool: { name: string }) => tool.name)
      .filter((name: string) => name !== "invalid")
      .sort();
    assert.deepEqual(child?.tools?.map((tool) => tool.name).sort(), actual);
  }
});

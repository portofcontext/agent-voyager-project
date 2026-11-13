import { trajectorySink } from "@agent-voyager-project/sdk/agent_cli";
import type { JsonValue } from "@agent-voyager-project/sdk/reports";
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
  parseTrajectory,
  finalOutput,
  type Trajectory,
  type Recording,
} from "@agent-voyager-project/sdk/trajectory";
import { run } from "../src/agent.js";
import { describe } from "../src/descriptor.js";
import { ScriptedModel, type Step } from "./scripted.js";
const artifactFiles = new WeakMap<Trajectory, Recording>();
function capture(recording: Recording): Trajectory {
  const trajectory = parseTrajectory(recording.trajectory);
  artifactFiles.set(trajectory, recording);
  return trajectory;
}
function effective(snapshots: Trajectory[]): any {
  const file = artifactFiles
    .get(snapshots.at(-1)!)
    ?.artifacts?.get("inputs/effective-agent.json");
  assert.ok(file);
  return JSON.parse(Buffer.from(file.content).toString("utf8"));
}
const MODEL = "gpt-4.1";
const fixture = fileURLToPath(
  new URL("../../../../../testing/mcp/avp_test_mcp.py", import.meta.url),
);

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
  const snapshots: Trajectory[] = [];
  let requestsAtStart: number | undefined;
  const previous = process.cwd();
  process.chdir(cwd);
  try {
    const work = run(
      received,
      async (event) => {
        await delay(1);
        if (meta(event.trajectory).started_at && requestsAtStart === undefined)
          requestsAtStart = model.requests.length;
        snapshots.push(capture(event)!);
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
    await trajectorySink(
      join(process.env.AVP_ATIF_CAPTURE, randomUUID(), "trajectory.json"),
    )(artifactFiles.get(latest(snapshots))!);
  }
  return {
    snapshots,
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
  assert.ok(d.tools?.some((t: any) => t.name === "write"));
  assert.ok(d.tools?.some((t: any) => t.name === "apply_patch"));
  assert.ok(!d.tools?.some((t: any) => t.name === "invalid"));
  assert.deepEqual(d.subagents?.map((a: any) => a.name).sort(), [
    "explore",
    "general",
  ]);
  assert.ok(d.subagents?.every((a: any) => a.tools?.length));
  assert.ok(d.skills?.some((s: any) => s.name === "customize-opencode"));
  assert.ok(d.supported_models?.some((m) => m.provider === "anthropic"));
});

test("native tool loop preserves response deltas, reported cost, and awaited sink order", async (t: any) => {
  const { snapshots, cwd, requests } = await drive(t, {}, (cwd) => [
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
  assert.equal(atifResponses(snapshots).length, 2);
  assert.equal(meta(latest(snapshots)).complete, true);
  const responses = atifResponses(snapshots);
  assert.equal(responses.length, 2);
  assert.deepEqual(
    responses.map((r) => r.metrics.prompt_tokens),
    [120, 200],
  );
  assert.deepEqual(
    responses.map((r) => r.metrics.completion_tokens),
    [30, 40],
  );
  assert.equal(responses[0]!.metrics.cached_tokens, 20);
  assert.ok(
    responses.every(
      (r) =>
        meta(r.metrics).cost_source === "reported" && r.metrics.cost_usd > 0,
    ),
  );
  assert.equal(atifResults(snapshots)[0]!.source_call_id, "write1");
  assert.equal(meta(atifResults(snapshots)[0]!).is_error, false);
  assert.equal(finalOutput(latest(snapshots)), "DONE");
  assert.equal(requests.length, 2);
});

test("native allowlists expose no tools or child agents when disabled", async (t: any) => {
  const { snapshots, requests } = await drive(
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
  const started = latest(snapshots).agent;
  assert.deepEqual(started.tool_definitions, []);
  assert.deepEqual(effective(snapshots).subagents, []);
  assert.deepEqual(effective(snapshots).skills, []);
  assert.ok(!requests[0]!.tools?.length);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("the full assembled default prompt is recorded before the model request", async (t: any) => {
  const { snapshots, requests, cwd, requestsAtStart } = await drive(t, {}, [
    { text: "OK" },
  ]);
  const actual = system(requests[0]!);
  assert.match(actual, /You are opencode/);
  assert.ok(actual.includes(cwd));
  assert.match(actual, /<env>/);
  assert.equal(
    latest(snapshots).steps.find((s: any) => s.source === "system")?.message,
    actual,
  );
  assert.equal(requestsAtStart, 0);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("explicit instructions replace the entire native prompt on every parent response", async (t: any) => {
  const { snapshots, requests, requestsAtStart } = await drive(
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
    latest(snapshots).steps.find((s: any) => s.source === "system")?.message,
    "ONLY_COMMISSION_INSTRUCTIONS",
  );
  assert.equal(requestsAtStart, 0);
  assert.equal(meta(atifResults(snapshots)[0]!).is_error, false);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("an empty system-prompt override sends no native system instructions", async (t: any) => {
  const { snapshots, requests, requestsAtStart } = await drive(
    t,
    { system_prompt: "" },
    [{ text: "OK" }],
  );
  assert.equal(requests.length, 1);
  assert.equal(system(requests[0]!), "");
  assert.equal(
    latest(snapshots).steps.find((s: any) => s.source === "system")?.message,
    "",
  );
  assert.equal(requestsAtStart, 0);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("a missing bundled prompt hook refuses the run before a model request", async (t: any) => {
  const hook = fileURLToPath(
    new URL("../src/prompt-plugin.js", import.meta.url),
  );
  renameSync(hook, `${hook}.disabled`);
  try {
    const { snapshots, requests } = await drive(
      t,
      { system_prompt: "ONLY_COMMISSION" },
      [],
    );
    assert.equal(requests.length, 0);
    assert.equal(meta(latest(snapshots)).started_at ? 1 : 0, 0);
    assert.match(
      atifErrors(snapshots)[0]!.message,
      /did not load.*system-prompt hook/,
    );
  } finally {
    renameSync(`${hook}.disabled`, hook);
  }
});

test("native skill activation uses commissioned SKILL.md and hides ambient skills", async (t: any) => {
  const { snapshots } = await drive(
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
  const skills = effective(snapshots).skills ?? [];
  assert.ok(skills.some((s: any) => s.name === "migration-check"));
  assert.ok(!skills.some((s: any) => s.name === "ambient"));
  assert.match(JSON.stringify(atifResults(snapshots)), /NATIVE_SKILL_BODY/);
});

test("native MCP tools retain server ownership, parallel call IDs, and both error forms", async (t: any) => {
  const { snapshots } = await drive(
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
  const started = latest(snapshots).agent;
  assert.equal(effective(snapshots).mcp_servers?.[0]?.status, "connected");
  assert.equal(
    meta(
      started.tool_definitions?.find(
        (t: any) => t.function.name === "avptest_Avptest_Echo",
      ),
    ).mcp_server_id,
    "avptest",
  );
  const returns = atifResults(snapshots);
  assert.equal(returns.length, 3);
  assert.equal(returns.filter((r) => meta(r).is_error).length, 2);
  assert.deepEqual(returns.map((r) => r.source_call_id).sort(), [
    "one",
    "three",
    "two",
  ]);
  assert.match(JSON.stringify(returns), /MCP_OK/);
});

test("native child responses are scoped individually without rolled-up double counting", async (t: any) => {
  const { snapshots, requests } = await drive(
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
  const child = atifChildren(snapshots)[0]!;
  const children = child.steps.filter((step: any) => step.source === "agent");
  assert.equal(children.length, 1);
  assert.equal(children[0]!.metrics.prompt_tokens, 300);
  assert.equal(meta(child).stop_reason, "converged");
  assert.match(JSON.stringify(child.steps), /CHILD_DONE/);
  assert.equal(atifResponses(snapshots).length, 3);
  assert.equal(system(requests[0]!), "PARENT_ONLY_PROMPT");
  assert.equal(system(requests[2]!), "PARENT_ONLY_PROMPT");
  assert.ok(!system(requests[1]!).includes("PARENT_ONLY_PROMPT"));
  assert.match(system(requests[1]!), /<env>/);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("native structured output is returned and its actual tool schema declared", async (t: any) => {
  const { snapshots } = await drive(
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
    latest(snapshots).agent.tool_definitions?.some(
      (t: any) => t.function.name === "StructuredOutput",
    ),
  );
  assert.deepEqual(finalOutput(latest(snapshots)), { answer: "OK" });
});

test("invalid Commission and missing environment credentials refuse before a provider request", async (t: any) => {
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
    const { snapshots, requests } = await drive(t, extra, []);
    assert.equal(requests.length, 0);
    assert.equal(meta(latest(snapshots)).started_at ? 1 : 0, 0);
    assert.ok(atifErrors(snapshots).length);
  }
});

test("failed native MCP connection stops before any model request", async (t: any) => {
  const { snapshots, requests } = await drive(
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
    meta(atifErrors(snapshots)[0]!).error_code,
    "mcp_connect_failed",
  );
});

test("native provider errors are classified without an invented response", async (t: any) => {
  const { snapshots } = await drive(t, {}, [
    { status: 401, body: { error: { message: "invalid API key" } } },
  ]);
  assert.equal(atifResponses(snapshots).length, 0);
  assert.equal(meta(atifErrors(snapshots)[0]!).error_code, "auth_error");
  assert.equal(meta(latest(snapshots)).stop_reason, "error");
});

test("cancellation closes the started run without a provider call", async (t: any) => {
  const controller = new AbortController();
  controller.abort();
  const { snapshots, requests } = await drive(t, {}, [], {
    signal: controller.signal,
  });
  assert.equal(requests.length, 0);
  assert.equal(meta(latest(snapshots)).stop_reason, "interrupted");
});

test("declared child tools match the native request when parent tools are restricted", async (t: any) => {
  const { snapshots, requests } = await drive(
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
  const child = effective(snapshots).subagents?.find(
    (a: any) => a.name === "general",
  );
  const native = (requests[1]!.tools ?? [])
    .map((tool: { name: string }) => tool.name)
    .filter((name: string) => name !== "invalid")
    .sort();
  assert.deepEqual(child?.tools?.map((tool: any) => tool.name).sort(), native);
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("native child tool snapshots stay within their invocation", async (t: any) => {
  const { snapshots } = await drive(
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
  const child = atifChildren(snapshots)[0]!;
  const childCalls = child.steps.flatMap((step: any) => step.tool_calls ?? []);
  const childResults = child.steps.flatMap(
    (step: any) => step.observation?.results ?? [],
  );
  assert.ok(childCalls.some((call: any) => call.tool_call_id === "readchild"));
  assert.ok(
    childResults.some((result: any) => result.source_call_id === "readchild"),
  );
  assert.match(JSON.stringify(childResults), /CHILD_FILE/);
  assert.equal(
    child.steps.filter((step: any) => step.source === "agent").length,
    2,
  );
  assert.ok(
    !latest(snapshots).steps.some((step: any) =>
      step.tool_calls?.some((call: any) => call.tool_call_id === "readchild"),
    ),
  );
});

test("interruption retains native streamed content and stops the server", async (t: any) => {
  const controller = new AbortController();
  const { snapshots } = await drive(
    t,
    {},
    [{ text: "PARTIAL ".repeat(100), chunkDelayMs: 100 }],
    { signal: controller.signal, abortAfterRequest: controller },
  );
  const response = atifResponses(snapshots)[0]!;
  assert.ok(String(response.message).includes("PARTIAL"));
  assert.ok(
    meta(response).duration_ms >= 100,
    `partial response duration: ${meta(response).duration_ms}`,
  );
  assert.equal(response.metrics?.cost_usd, undefined);
  assert.deepEqual(meta(response).finish_reasons, ["aborted"]);
  assert.equal(meta(latest(snapshots)).stop_reason, "interrupted");
});

test("project configuration and plugin discovery stay outside the commissioned runtime", async (t: any) => {
  const { cwd, requests, snapshots } = await drive(
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
  assert.equal(meta(latest(snapshots)).stop_reason, "converged");
});

test("native API requests use proxy stand-ins and resolved environment credentials", async (t: any) => {
  for (const [credential, env, expected] of [
    [{ proxy: "standin-key" }, {}, "standin-key"],
    [
      { env: "AVP_OPENCODE_TEST_KEY" },
      { AVP_OPENCODE_TEST_KEY: "environment-test-key" },
      "environment-test-key",
    ],
  ] as const) {
    const { headers, snapshots } = await drive(
      t,
      { model: { credential } },
      [{ text: "OK" }],
      { env },
    );
    assert.equal(headers[0]!.authorization, `Bearer ${expected}`);
    if ("env" in credential)
      assert.ok(!JSON.stringify(snapshots).includes(expected));
  }
});

test("native reasoning tokens are included once in output usage", async (t: any) => {
  const { snapshots } = await drive(t, {}, [
    {
      text: "DONE",
      usage: { input: 120, cached: 20, output: 30, reasoning: 10 },
    },
  ]);
  const usage = atifResponses(snapshots)[0]!.metrics;
  assert.equal(usage.completion_tokens, 30);
  assert.equal(meta(usage).reasoning_output_tokens, 10);
  assert.equal(usage.prompt_tokens, 120);
});

test("unknown providers are refused before native provider initialization", async (t: any) => {
  const { snapshots, requests } = await drive(
    t,
    { model: { provider: "avp-unsupported-provider" } },
    [],
  );
  assert.equal(requests.length, 0);
  assert.equal(meta(latest(snapshots)).started_at ? 1 : 0, 0);
  assert.equal(
    meta(atifErrors(snapshots)[0]!).error_code,
    "invalid_commission",
  );
});

test("each declared native child catalog matches the actual model tools", async (t: any) => {
  for (const subagent_type of ["general", "explore"]) {
    const { snapshots, requests } = await drive(t, {}, [
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
    const child = effective(snapshots).subagents?.find(
      (agent: any) => agent.name === subagent_type,
    );
    const actual = (requests[1]!.tools ?? [])
      .map((tool: { name: string }) => tool.name)
      .filter((name: string) => name !== "invalid")
      .sort();
    assert.deepEqual(
      child?.tools?.map((tool: any) => tool.name).sort(),
      actual,
    );
  }
});

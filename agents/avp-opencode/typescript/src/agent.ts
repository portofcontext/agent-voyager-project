import { pathToFileURL } from "node:url";
import type { TrajectorySink } from "@agent-voyager-project/sdk/trajectory";
/** The native OpenCode server owns model calls, tools, and the loop. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, isAbsolute } from "node:path";
import { Recorder, RecorderError } from "@agent-voyager-project/sdk/recorder";
import type { JsonValue } from "@agent-voyager-project/sdk/reports";
import { loadPrices } from "@agent-voyager-project/sdk/utils/pricing";
import { planRun } from "@agent-voyager-project/sdk/utils/run_plan";
import {
  BUNDLED,
  configuration,
  MissingSecret,
  toolSwitches,
} from "./commission.js";
import { catalog, children, describe, nativeSkills } from "./descriptor.js";
import { McpFailure, discover } from "./mcp.js";
import { Server, data } from "./server.js";
import { EventClock, SessionEvents } from "./session.js";
import { SystemPrompt } from "./system-prompt.js";
import * as translate from "./translate.js";
export interface RunOptions {
  signal?: AbortSignal;
  env?: Record<string, string | undefined>;
}
export async function run(
  received: JsonValue,
  sink: TrajectorySink,
  options: RunOptions = {},
): Promise<void> {
  const clock = new EventClock();
  const rec = new Recorder(sink, {
    prices: await loadPrices(),
    now: clock.now,
  });
  const descriptor = await describe();
  const commission = await rec.begin(received, descriptor);
  if (!commission) return;
  if (
    !descriptor.supported_models?.some(
      (model) => model.provider === commission.model.provider,
    )
  ) {
    await rec.error(
      "invalid_commission",
      "OpenCode has no bundled SDK for this provider",
    );
    return;
  }
  const plan = planRun(commission, descriptor);
  if (
    commission.output_schema != null &&
    commission.output_schema.type !== "object"
  ) {
    await rec.error(
      "invalid_commission",
      "OpenCode structured output requires an object schema",
    );
    return;
  }
  const scratch = mkdtempSync(join(tmpdir(), "avp-opencode-"));
  let server: Server | undefined;
  let prompt: SystemPrompt | undefined;
  let started: Promise<void> | undefined;
  let startRun: ((system?: string) => Promise<void>) | undefined;
  const events = new AbortController();
  let interrupted = options.signal?.aborted ?? false;
  let sessionID: string | undefined;
  let observer: SessionEvents | undefined;
  const abortNative = async () => {
    if (sessionID && server) await server.client.session.abort({ sessionID });
  };
  const abort = () => {
    interrupted = true;
    void abortNative().catch(() => {});
    setTimeout(() => events.abort(), 10_000).unref();
  };
  options.signal?.addEventListener("abort", abort, { once: true });
  try {
    const env = { ...process.env, ...options.env };
    prompt = await SystemPrompt.open(commission.system_prompt, (system) =>
      startRun!(system),
    );
    server = await Server.start({
      cwd: process.cwd(),
      scratch,
      config: configuration(commission, plan, scratch, env),
      env: options.env,
      prompt: prompt.pluginOptions,
    });
    const client = server.client;
    const providers = await data(client.provider.list());
    const provider = providers.all.find(
      (p) => p.id === commission.model.provider,
    );
    const model = provider?.models[commission.model.id];
    if (!model || !BUNDLED.has(model.api.npm)) {
      await rec.error(
        "invalid_commission",
        "OpenCode cannot serve this model with a bundled provider SDK",
      );
      return;
    }
    if (!providers.connected.includes(commission.model.provider)) {
      await rec.error(
        "auth_error",
        `no credentials for ${commission.model.provider}`,
      );
      return;
    }
    const offered = await catalog(
      client,
      commission.model.provider,
      commission.model.id,
    );
    const allowed = new Set(plan.started.tools?.map((t) => t.name) ?? []);
    if (!plan.started.subagents?.length) allowed.delete("task");
    const enabled = offered.filter((t) => allowed.has(t.name));
    if (
      commission.skills?.length &&
      !enabled.some((tool) => tool.name === "skill")
    ) {
      await rec.error(
        "invalid_commission",
        "OpenCode needs its skill tool to activate commissioned skills",
      );
      return;
    }
    const off = (await data(client.tool.ids())).filter(
      (name) => !enabled.some((t) => t.name === name),
    );
    const status = await data(client.mcp.status());
    for (const item of commission.mcp_servers ?? [])
      if (status[item.id]?.status !== "connected")
        throw new McpFailure(`${item.id}: native MCP connection failed`);
    const mcpTools = await discover(
      commission,
      env,
      new Set(offered.map((t) => t.name)),
    );
    const selectedSkills = (await nativeSkills(client)).filter((s) =>
      plan.started.skills?.some((item) => item.name === s.name),
    );
    for (const skill of selectedSkills) {
      if (!isAbsolute(skill.location))
        await rec.artifact(
          `inputs/skills/${encodeURIComponent(skill.name)}/instructions.md`,
          Buffer.from(skill.content),
          "input",
        );
    }
    const skills = selectedSkills.map(({ name, description, location }) => ({
      name,
      description: description ?? "",
      ...(isAbsolute(location)
        ? { source: pathToFileURL(dirname(location)).href }
        : {
            instructions_path: `inputs/skills/${encodeURIComponent(name)}/instructions.md`,
          }),
    }));
    if (
      commission.skills?.some((s) => !skills.some((n) => n.name === s.name))
    ) {
      await rec.error(
        "invalid_commission",
        "OpenCode did not load all commissioned skills",
      );
      return;
    }
    const agentList = await data(client.app.agents());
    const agents = children(
      agentList,
      [...offered, ...mcpTools],
      skills,
      toolSwitches(
        off,
        enabled.map((t) => t.name),
      ),
    ).filter((a) => plan.started.subagents?.some((s) => s.name === a.name));
    const outputTool = commission.output_schema
      ? {
          name: "StructuredOutput",
          inputSchema: Object.fromEntries(
            Object.entries(commission.output_schema).filter(
              ([key]) => key !== "$schema",
            ),
          ) as { type: "object" },
        }
      : undefined;
    if (!prompt.ready)
      throw new Error("OpenCode did not load the bundled system-prompt hook");
    const settings = {
      ...plan.started,
      tools: [...enabled, ...mcpTools, ...(outputTool ? [outputTool] : [])],
      skills,
      subagents: agents,
      mcp_servers: plan.started.mcp_servers?.map((s) => ({
        ...s,
        status: "connected" as const,
      })),
    };
    startRun = (system) =>
      (started ??= rec.start({ ...settings, system_prompt: system }));
    if (interrupted) {
      await startRun(commission.system_prompt ?? undefined);
      await rec.stop("interrupted");
      return;
    }
    const created = await data(
      client.session.create({ title: `avp ${commission.run_id}` }),
    );
    sessionID = created.id;
    prompt.sessionID = sessionID;
    const subscription = await client.event.subscribe(
      {},
      { signal: events.signal },
    );
    const iterator = subscription.stream[Symbol.asyncIterator]();
    await iterator.next();
    observer = new SessionEvents(
      rec,
      clock,
      sessionID,
      new Set(agents.map((a) => a.name)),
      abortNative,
    );
    const request = await client.session.promptAsync({
      sessionID,
      model: {
        providerID: commission.model.provider,
        modelID: commission.model.id,
      },
      agent: "build",
      parts: [{ type: "text", text: commission.prompt }],
      tools: toolSwitches(
        off,
        enabled.map((t) => t.name),
      ),
      ...(commission.output_schema
        ? { format: { type: "json_schema", schema: commission.output_schema } }
        : {}),
    });
    if (request.error)
      throw new Error(
        `OpenCode rejected the prompt: ${JSON.stringify(request.error)}`,
      );
    const exited = server.exited.then((why) => {
      throw new Error(why);
    });
    while (!observer.idle) {
      const next = await Promise.race([iterator.next(), exited]);
      if (next.done)
        throw new Error(
          "OpenCode event stream ended before the session became idle",
        );
      await observer.handle(next.value);
    }
    if (prompt.failure) throw prompt.failure;
    if (!started) {
      if (interrupted) await startRun(commission.system_prompt ?? undefined);
      else
        throw (
          observer.failure ??
          new Error("OpenCode ended before its system-prompt hook ran")
        );
    }
    await started;
    if (!interrupted) observer.check();
    if (interrupted) {
      await observer.flushInterrupted();
      await rec.stop("interrupted");
    } else if (observer.failure || observer.lastError) {
      const error = observer.failure ?? observer.lastError;
      await rec.error(translate.errorCode(error), translate.errorText(error));
      await rec.stop("error");
    } else await rec.stop("converged", observer.output);
  } catch (error) {
    if (rec.ended) throw error;
    if (interrupted) {
      await observer?.flushInterrupted();
      await rec.stop("interrupted");
      return;
    }
    await rec.error(
      error instanceof MissingSecret
        ? "auth_error"
        : error instanceof McpFailure
          ? "mcp_connect_failed"
          : error instanceof RecorderError
            ? "agent_crash"
            : translate.errorCode(error),
      translate.errorText(error),
    );
    await rec.stop("error");
    if (error instanceof RecorderError) throw error;
  } finally {
    options.signal?.removeEventListener("abort", abort);
    events.abort();
    await server?.close();
    await prompt?.close();
    rmSync(scratch, { recursive: true, force: true });
  }
}

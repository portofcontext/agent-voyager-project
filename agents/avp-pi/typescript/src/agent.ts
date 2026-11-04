/** Pi owns the loop; native events are serialized through the SDK Recorder. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Recorder } from "@agent-voyager-project/sdk/recorder";
import { planRun } from "@agent-voyager-project/sdk/utils/run_plan";
import type { Commission } from "@agent-voyager-project/sdk/commission";
import type { Tool } from "@agent-voyager-project/sdk/descriptor";
import type {
  EventSink,
  JsonValue,
} from "@agent-voyager-project/sdk/trajectory";
import type { AssistantMessage } from "@earendil-works/pi-ai";
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
  type AgentSession,
  type ModelRuntime,
  type ToolDefinition,
} from "@earendil-works/pi-coding-agent";
import {
  McpClient,
  StdioTransport,
  StreamableHttpTransport,
  toLlmContent,
} from "@earendil-works/pi-mcp";
import * as cm from "./commission.js";
import { describe, runtime, VERSION } from "./descriptor.js";
import * as translate from "./translate.js";

export interface RunOptions {
  modelRuntime?: ModelRuntime;
  agentDir?: string;
}
class McpConnectError extends Error {}

async function connect(
  commission: Commission,
  clients: McpClient[],
  taken: Set<string>,
  signal: AbortSignal,
): Promise<{ definitions: ToolDefinition[]; declarations: Tool[] }> {
  const definitions: ToolDefinition[] = [];
  const declarations: Tool[] = [];
  for (const server of commission.mcp_servers ?? []) {
    const client = new McpClient({
      name: cm.AGENT_NAME,
      version: VERSION,
      requestTimeoutMs: 30_000,
    });
    clients.push(client);
    try {
      const transport =
        server.type === "stdio"
          ? new StdioTransport({
              command: server.command[0]!,
              args: server.command.slice(1),
              env: Object.fromEntries(
                Object.entries(server.env ?? {}).map(([k, v]) => [
                  k,
                  typeof v === "string" ? v : cm.envSecret(v),
                ]),
              ),
              inheritEnv: true,
              stderr: "pipe",
            })
          : new StreamableHttpTransport({
              url: server.url,
              headers: Object.fromEntries(
                Object.entries(server.headers ?? {})
                  .filter(([, v]) => typeof v === "string" || !("proxy" in v))
                  .map(([k, v]) => [
                    k,
                    typeof v === "string"
                      ? v
                      : cm.envSecret(v as { env: string }),
                  ]),
              ),
            });
      await client.connect(transport);
      for (const tool of await client.listTools({ signal })) {
        const name = cm.toolName(server.id, tool.name, taken);
        if (taken.has(name))
          throw new Error(`duplicate MCP tool name: ${name}`);
        taken.add(name);
        definitions.push({
          name,
          label: `${server.id}/${tool.name}`,
          description: tool.description ?? "",
          parameters: tool.inputSchema as ToolDefinition["parameters"],
          outputSchema: tool.outputSchema as
            ToolDefinition["parameters"] | undefined,
          async execute(_id, args, requestSignal) {
            const result = await client.callTool(
              tool.name,
              args as Record<string, unknown>,
              {
                signal: requestSignal,
              },
            );
            return {
              content: toLlmContent(result),
              details: { server: server.id, tool: tool.name },
              isError: result.isError ?? false,
              structuredContent:
                result.structuredContent === undefined
                  ? undefined
                  : JSON.parse(JSON.stringify(result.structuredContent)),
            };
          },
        });
        declarations.push({
          name,
          description: tool.description ?? "",
          inputSchema: JSON.parse(JSON.stringify(tool.inputSchema)),
          ...(tool.outputSchema
            ? { outputSchema: JSON.parse(JSON.stringify(tool.outputSchema)) }
            : {}),
          mcp_server_id: server.id,
        });
      }
    } catch (error) {
      if (error instanceof cm.MissingSecret) throw error;
      throw new McpConnectError(
        `${server.id}: ${error instanceof Error ? error.message : String(error)}`,
        { cause: error },
      );
    }
  }
  return { definitions, declarations };
}

export async function run(
  received: JsonValue,
  sink: EventSink,
  signal: AbortSignal,
  options: RunOptions = {},
): Promise<void> {
  const descriptor = await describe();
  const rec = new Recorder(sink);
  const commission = await rec.begin(received, descriptor);
  if (!commission) return;
  if (commission.output_schema != null) {
    await rec.error(
      "invalid_commission",
      "Pi has no native structured-output interface for output_schema",
    );
    return;
  }
  const plan = planRun(commission, descriptor);
  const clients: McpClient[] = [];
  const scratch = mkdtempSync(join(tmpdir(), "avp-pi-"));
  let session: AgentSession | undefined;
  let unsubscribe: (() => void) | undefined;
  let reports = Promise.resolve();
  let reportingError: unknown;
  const abort = () => {
    void session?.abort();
    for (const client of clients) void client.close();
  };
  signal.addEventListener("abort", abort, { once: true });
  try {
    const models = options.modelRuntime ?? (await runtime());
    const key = cm.credential(commission);
    if (key !== undefined)
      await models.setRuntimeApiKey(commission.model.provider, key);
    const found = models.getModel(
      commission.model.provider,
      commission.model.id,
    );
    if (!found) {
      await rec.error(
        "invalid_commission",
        "model is not in Pi's bundled catalog",
      );
      return;
    }
    const model = commission.model.base_url
      ? { ...found, baseUrl: commission.model.base_url }
      : found;
    const mcp = await connect(
      commission,
      clients,
      new Set((descriptor.tools ?? []).map((t) => t.name)),
      signal,
    );
    const settings = SettingsManager.inMemory({
      enableInstallTelemetry: false,
      cacheWarming: "off",
      compaction: { enabled: false },
    });
    let effectivePrompt = "";
    const loader = new DefaultResourceLoader({
      cwd: process.cwd(),
      agentDir: options.agentDir ?? scratch,
      settingsManager: settings,
      noExtensions: true,
      noSkills: true,
      noPromptTemplates: true,
      noThemes: true,
      noContextFiles: true,
      extensionFactories: [
        (pi) => {
          pi.on("before_agent_start", () => ({
            systemPrompt: effectivePrompt,
          }));
        },
      ],
    });
    await loader.reload();
    const names = [
      ...(plan.started.tools ?? []).map((t) => t.name),
      ...mcp.definitions.map((t) => t.name),
    ];
    ({ session } = await createAgentSession({
      cwd: process.cwd(),
      agentDir: options.agentDir ?? scratch,
      model,
      modelRuntime: models,
      resourceLoader: loader,
      tools: names,
      customTools: mcp.definitions,
      sessionManager: SessionManager.inMemory(process.cwd()),
      settingsManager: settings,
    }));
    await session.bindExtensions({});
    effectivePrompt = [
      commission.system_prompt ?? session.systemPrompt,
      cm.skillInstructions(commission),
    ]
      .filter(Boolean)
      .join("\n\n");
    const active = new Set(session.getActiveToolNames());
    const managed = new Map(mcp.declarations.map((t) => [t.name, t]));
    const tools: Tool[] = session
      .getAllTools()
      .filter((t) => active.has(t.name))
      .map((t) => ({
        name: t.name,
        description: t.description,
        inputSchema: JSON.parse(JSON.stringify(t.parameters)),
        ...(managed.get(t.name)?.outputSchema
          ? { outputSchema: managed.get(t.name)!.outputSchema }
          : {}),
        ...(managed.has(t.name)
          ? { mcp_server_id: managed.get(t.name)!.mcp_server_id }
          : {}),
      }));
    await rec.start({
      ...plan.started,
      system_prompt: effectivePrompt,
      tools: tools.length ? tools : undefined,
      mcp_servers: plan.started.mcp_servers?.map((s) => ({
        ...s,
        status: "connected",
      })),
    });
    const pending = new Set<string>();
    let started = performance.now();
    let last: AssistantMessage | undefined;
    unsubscribe = session.subscribe((event) => {
      const ended = performance.now();
      if (event.type === "message_start" && event.message.role === "assistant")
        started = ended;
      const duration = Math.max(0, Math.trunc(ended - started));
      if (event.type === "message_end" && event.message.role === "assistant")
        last = event.message;
      reports = reports
        .then(async () => {
          if (reportingError !== undefined) return;
          if (
            event.type === "message_end" &&
            event.message.role === "assistant"
          ) {
            const message = event.message;
            if (
              message.stopReason === "error" ||
              message.stopReason === "aborted"
            )
              return;
            if (
              message.stopReason === "pending" ||
              message.stopReason === "deferred"
            )
              throw new Error(
                "Pi deferred model responses cannot be recorded by this adapter",
              );
            const actual = message.responseModel ?? message.model;
            await rec.response(translate.content(message.content), {
              usage: translate.usage(message.usage),
              responseModel:
                actual !== commission.model.id ? actual : undefined,
              finishReasons: [message.rawStopReason ?? message.stopReason],
              durationMs: duration,
            });
            for (const block of message.content)
              if (block.type === "toolCall") pending.add(block.id);
          } else if (
            event.type === "tool_execution_end" &&
            pending.delete(event.toolCallId)
          ) {
            const structured = event.result.structuredContent;
            await rec.toolReturned(
              event.toolCallId,
              translate.toolContent(event.result.content),
              {
                isError: event.isError,
                structuredContent:
                  structured &&
                  typeof structured === "object" &&
                  !Array.isArray(structured)
                    ? JSON.parse(JSON.stringify(structured))
                    : undefined,
              },
            );
          } else if (
            event.type === "message_end" &&
            event.message.role === "toolResult" &&
            pending.delete(event.message.toolCallId)
          ) {
            await rec.toolReturned(
              event.message.toolCallId,
              translate.toolContent(event.message.content),
              { isError: event.message.isError },
            );
          } else if (event.type === "compaction_start") {
            throw new Error(
              "Pi context compaction cannot be recorded by this adapter",
            );
          }
        })
        .catch((error) => {
          reportingError ??= error;
          void session?.abort();
        });
    });
    if (!signal.aborted) await session.prompt(commission.prompt);
    await reports;
    if (reportingError !== undefined) throw reportingError;
    if (signal.aborted || last?.stopReason === "aborted")
      await rec.stop("interrupted");
    else if (last?.stopReason === "error") {
      await rec.error(
        translate.errorCode(last.errorMessage ?? "provider error"),
        last.errorMessage ?? "provider error",
      );
      await rec.stop("error");
    } else if (pending.size)
      throw new Error("Pi ended with incomplete tool results");
    else
      await rec.stop(
        last?.rawStopReason === "refusal" ||
          last?.rawStopReason === "content_filter"
          ? "refused"
          : "converged",
        session.getLastAssistantText(),
      );
  } catch (error) {
    await reports;
    if (signal.aborted && reportingError === undefined) {
      await rec.stop("interrupted");
      return;
    }
    const code =
      error instanceof cm.MissingSecret
        ? "auth_error"
        : error instanceof McpConnectError
          ? "mcp_connect_failed"
          : translate.errorCode(error);
    if (!rec.ended) {
      await rec.error(
        code,
        error instanceof Error ? error.message : String(error),
      );
      await rec.stop("error");
    }
    if (code === "agent_crash") throw error;
  } finally {
    signal.removeEventListener("abort", abort);
    unsubscribe?.();
    session?.dispose();
    await Promise.allSettled(clients.map((client) => client.close()));
    rmSync(scratch, { recursive: true, force: true });
  }
}

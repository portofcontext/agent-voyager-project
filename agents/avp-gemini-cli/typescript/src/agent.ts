/** Observe Gemini's session, scheduler, and generator; never drive its tool loop. */
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as core from "@google/gemini-cli-core";
import { isSubagentProgress } from "@google/gemini-cli-core/dist/src/agents/types.js";
import { getToolCallContext } from "@google/gemini-cli-core/dist/src/utils/toolCallContext.js";
import { Recorder, RecorderError } from "@agent-voyager-project/sdk/recorder";
import type { Commission } from "@agent-voyager-project/sdk/commission";
import type {
  ContentBlock,
  EventSink,
  JsonValue,
  SubagentUsage,
} from "@agent-voyager-project/sdk/trajectory";
import { planRun } from "@agent-voyager-project/sdk/utils/run_plan";
import {
  computeCost,
  loadPrices,
  type Prices,
} from "@agent-voyager-project/sdk/utils/pricing";
import { credential, MissingSecret } from "./commission.js";
import { describe, tools, skills, subagents } from "./descriptor.js";
import { configure, isolated } from "./native.js";
import * as translate from "./translate.js";

export interface RunOptions {
  contentGenerator?: core.ContentGenerator;
  signal?: AbortSignal;
}
export async function run(
  received: JsonValue,
  sink: EventSink,
  options: RunOptions = {},
): Promise<void> {
  const prices = await loadPrices();
  const rec = new Recorder(sink, { prices });
  const descriptor = await describe();
  const commission = await rec.begin(received, descriptor);
  if (!commission) return;
  if (commission.output_schema != null) {
    await rec.error(
      "invalid_commission",
      "Gemini CLI has no native final structured-output interface exposed by this adapter",
    );
    return;
  }
  const plan = planRun(commission, descriptor);
  const scratch = mkdtempSync(join(tmpdir(), "avp-gemini-cli-"));
  const home = join(scratch, "home");
  let session: core.LegacyAgentSession | undefined;
  const abort = () => session?.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  try {
    await isolated(
      home,
      async () => {
        const config = await configure(
          home,
          process.cwd(),
          commission.run_id,
          commission.model.id,
          commission,
          plan,
        );
        let scheduler: core.Scheduler | undefined;
        try {
          await config.refreshAuth(
            core.AuthType.USE_GEMINI,
            credential(commission),
            commission.model.base_url ?? undefined,
          );
          if (options.contentGenerator)
            config.getContentGenerator = () => options.contentGenerator!;
          const manager = config.getMcpClientManager();
          for (const server of commission.mcp_servers ?? []) {
            if (
              manager?.getClient(server.id)?.getStatus() !==
              core.MCPServerStatus.CONNECTED
            ) {
              await rec.error(
                "mcp_connect_failed",
                `${server.id}: ${manager?.getLastError(server.id) ?? "could not connect"}`,
              );
              return;
            }
          }
          const loaded = new Set(skills(config).map((skill) => skill.name));
          if (commission.skills?.some((skill) => !loaded.has(skill.name))) {
            await rec.error(
              "invalid_commission",
              "Gemini could not load all commissioned skills",
            );
            return;
          }
          const declared = tools(config, commission.model.id);
          if (
            commission.skills?.length &&
            !declared.some((tool) => tool.name === "activate_skill")
          ) {
            await rec.error(
              "invalid_commission",
              "Gemini needs activate_skill to load commissioned skills",
            );
            return;
          }
          await rec.start({
            ...plan.started,
            system_prompt: core.getCoreSystemPrompt(
              config,
              config.getSystemInstructionMemory(),
            ),
            tools: declared,
            skills: skills(config),
            subagents: subagents(config, commission.model.id),
            mcp_servers: plan.started.mcp_servers?.map((server) => ({
              ...server,
              status: "connected",
            })),
          });
          const observer = new Observer(rec, config, commission, prices);
          const observedGenerator = observer.generator(
            config.getContentGenerator(),
          );
          config.getContentGenerator = () => observedGenerator;
          scheduler = new core.Scheduler({
            context: config,
            messageBus: config.getMessageBus(),
            getPreferredEditor: () => undefined,
            schedulerId: core.ROOT_SCHEDULER_ID,
          });
          const schedule = scheduler.schedule.bind(scheduler);
          scheduler.schedule = async (...args) => {
            const completed = await schedule(...args);
            await observer.completed(completed);
            return completed;
          };
          session = new core.LegacyAgentSession({
            config,
            client: observer.client(config.getGeminiClient()),
            scheduler,
            promptId: config.getSessionId(),
          });
          let end: string | undefined;
          let fatal: string | undefined;
          if (!options.signal?.aborted) {
            for await (const event of session.sendStream({
              message: { content: [{ type: "text", text: commission.prompt }] },
            })) {
              if (event.type === "error" && event.fatal) fatal = event.message;
              if (event.type === "agent_end") end = event.reason;
            }
          }
          if (options.signal?.aborted || end === "aborted")
            await rec.stop("interrupted");
          else if (
            observer.adapterFailure ||
            observer.failure ||
            fatal ||
            end === "failed" ||
            end === "max_turns" ||
            !end
          ) {
            const error =
              observer.adapterFailure ??
              observer.failure ??
              fatal ??
              `Gemini ended the run: ${end ?? "no terminal event"}`;
            await rec.error(translate.errorCode(error), error);
            await rec.stop("error");
          } else
            await rec.stop(
              end === "refusal" ? "refused" : "converged",
              observer.lastText,
            );
        } finally {
          scheduler?.dispose();
          await config.dispose();
        }
      },
      commission.system_prompt,
    );
  } catch (error) {
    if (rec.ended) throw error;
    if (options.signal?.aborted) {
      await rec.stop("interrupted");
      return;
    }
    const code =
      error instanceof MissingSecret
        ? "auth_error"
        : error instanceof RecorderError
          ? "agent_crash"
          : translate.errorCode(error);
    await rec.error(
      code,
      error instanceof Error ? error.message : String(error),
    );
    await rec.stop("error");
    if (error instanceof RecorderError) throw error;
  } finally {
    options.signal?.removeEventListener("abort", abort);
    rmSync(scratch, { recursive: true, force: true });
  }
}

type NativeResponse = Awaited<
  ReturnType<core.ContentGenerator["generateContent"]>
>;
interface Child {
  input: number;
  output: number;
  cache: number;
  reasoning: number;
  cost: number;
  priced: boolean;
  responses: number;
}
class Observer {
  failure?: string;
  adapterFailure?: string;
  lastText = "";
  private content: ContentBlock[] = [];
  private responseModel?: string;
  private opened = performance.now();
  private frames = new Map<string, Child>();
  constructor(
    private rec: Recorder,
    private config: core.Config,
    private commission: Commission,
    private prices: Prices,
  ) {}
  client(client: core.GeminiClient): core.GeminiClient {
    const self = this;
    return new Proxy(client, {
      get(target, key) {
        if (key === "sendMessageStream")
          return (
            ...args: Parameters<core.GeminiClient["sendMessageStream"]>
          ) => self.stream(target.sendMessageStream(...args));
        const value = Reflect.get(target, key, target);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
  }
  private fail(message: string): never {
    this.adapterFailure = message;
    throw new Error(message);
  }
  private childFor(role: string): Child | undefined {
    if (role === "main") return;
    if (role !== "subagent")
      this.fail(`Gemini utility model calls cannot be recorded: ${role}`);
    const id = getToolCallContext()?.callId;
    const child = id ? this.frames.get(id) : undefined;
    if (child) return child;
    // Nested native tool contexts can hide the root invocation. A single root
    // is unambiguous; concurrent roots must never be charged by opening order.
    if (this.frames.size === 1) return this.frames.values().next().value;
    return this.fail(
      "cannot attribute Gemini subagent model usage to one invocation",
    );
  }
  generator(inner: core.ContentGenerator): core.ContentGenerator {
    const self = this;
    return new Proxy(inner, {
      get(target, key) {
        if (key === "generateContentStream")
          return async (
            ...args: Parameters<core.ContentGenerator["generateContentStream"]>
          ) => {
            const [request, , role] = args;
            const child = self.childFor(role);
            if (!child && request.model !== self.commission.model.id)
              self.fail(
                `Gemini changed the commissioned model to ${request.model}`,
              );
            if (!child) self.responseModel = undefined;
            const stream = await target.generateContentStream(...args);
            return (async function* () {
              let final: NativeResponse | undefined;
              for await (const chunk of stream) {
                if (!child && chunk.modelVersion)
                  self.responseModel = chunk.modelVersion;
                if (chunk.usageMetadata) final = chunk;
                yield chunk;
              }
              if (child) self.childResponse(child, request.model, final);
            })();
          };
        if (key === "generateContent")
          return async (
            ...args: Parameters<core.ContentGenerator["generateContent"]>
          ) => {
            const child = self.childFor(args[2]);
            if (!child)
              self.fail("unexpected non-streaming Gemini main response");
            const response = await target.generateContent(...args);
            self.childResponse(child!, args[0].model, response);
            return response;
          };
        const value = Reflect.get(target, key, target);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
  }
  private childResponse(
    child: Child,
    model: string,
    response?: NativeResponse,
  ): void {
    let u;
    try {
      u = translate.usage(response?.usageMetadata);
    } catch (error) {
      this.fail(String(error));
    }
    const [cost, source] = computeCost(
      this.prices,
      { provider: "google", id: model },
      {
        inputTokens: u.input_tokens,
        outputTokens: u.output_tokens,
        cacheReadInputTokens: u.cache_read_input_tokens ?? undefined,
        responseModel: response?.modelVersion,
      },
    );
    child.input += u.input_tokens;
    child.output += u.output_tokens;
    child.cache += u.cache_read_input_tokens ?? 0;
    child.reasoning += u.reasoning_output_tokens ?? 0;
    child.responses++;
    child.cost += cost;
    child.priced &&= source === "computed";
  }
  async completed(calls: readonly core.CompletedToolCall[]): Promise<void> {
    for (const call of calls) {
      const content = translate.toolContent(call.response.responseParts);
      const child = this.frames.get(call.request.callId);
      const progress = isSubagentProgress(call.response.resultDisplay)
        ? call.response.resultDisplay
        : undefined;
      const interrupted =
        call.status === "cancelled" || progress?.state === "cancelled";
      const isError =
        call.status !== "success" ||
        call.response.error !== undefined ||
        progress?.state === "error" ||
        (progress?.terminateReason != null &&
          progress.terminateReason !== "GOAL");
      if (child) {
        this.frames.delete(call.request.callId);
        const usage: SubagentUsage = {
          input_tokens: child.input,
          output_tokens: child.output,
          cache_read_input_tokens: child.cache,
          reasoning_output_tokens: child.reasoning,
          responses: child.responses,
          cost_source: child.priced ? "computed" : "unknown",
          ...(child.priced ? { cost_usd: child.cost } : {}),
        };
        const text = content
          .map((block) => (block.type === "text" ? block.text : ""))
          .join("");
        await this.rec.subagentReturned(
          call.request.callId,
          text,
          interrupted ? "interrupted" : isError ? "error" : "converged",
          { usage: child.responses ? usage : undefined },
        );
      }
      await this.rec.toolReturned(call.request.callId, content, { isError });
    }
  }
  private async *stream(
    stream: AsyncGenerator<core.ServerGeminiStreamEvent>,
  ): AsyncGenerator<core.ServerGeminiStreamEvent> {
    this.opened = performance.now();
    for await (const event of stream) {
      switch (event.type) {
        case "retry":
          this.content = [];
          this.failure = undefined;
          this.opened = performance.now();
          break;
        case "thought":
          translate.append(this.content, {
            type: "thinking",
            thinking: [event.value.subject, event.value.description]
              .filter(Boolean)
              .join("\n"),
          });
          break;
        case "content":
          translate.append(this.content, { type: "text", text: event.value });
          break;
        case "tool_call_request":
          this.content.push({
            type: "tool_use",
            id: event.value.callId,
            name: event.value.name,
            input: event.value.args as Record<string, JsonValue>,
          });
          break;
        case "finished": {
          const content = this.content;
          this.content = [];
          await this.rec.response(content, {
            usage: translate.usage(event.value.usageMetadata),
            responseModel: this.responseModel,
            finishReasons: event.value.reason
              ? [event.value.reason]
              : undefined,
            durationMs: Math.max(
              0,
              Math.trunc(performance.now() - this.opened),
            ),
          });
          await this.rec.closeResponse();
          this.failure = undefined;
          this.lastText = content
            .flatMap((block) => (block.type === "text" ? [block.text] : []))
            .join("");
          for (const block of content) {
            if (block.type !== "tool_use" || block.name !== "invoke_agent")
              continue;
            const name = String(block.input.agent_name ?? "");
            if (!this.config.getAgentRegistry().getDefinition(name)) continue;
            await this.rec.subagentInvoked(block.id, name, block.input);
            this.frames.set(block.id, {
              input: 0,
              output: 0,
              cache: 0,
              reasoning: 0,
              cost: 0,
              priced: true,
              responses: 0,
            });
          }
          this.opened = performance.now();
          break;
        }
        case "error":
          this.failure = String(
            (event.value.error as { message?: string })?.message ??
              event.value.error,
          );
          this.content = [];
          break;
        case "invalid_stream":
          this.failure = event.value.message || event.value.type;
          this.content = [];
          break;
        case "context_window_will_overflow":
          this.failure = "Gemini context window will overflow";
          break;
        case "chat_compressed":
          this.fail(
            "Gemini context compaction cannot be recorded by this adapter",
          );
      }
      yield event;
    }
  }
}

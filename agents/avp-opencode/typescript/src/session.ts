/** Translate native complete responses and tools, including child sessions. */
import type {
  AssistantMessage,
  Event,
  Part,
  StepFinishPart,
  ToolPart,
} from "@opencode-ai/sdk/v2/client";
import type { Recorder } from "@agent-voyager-project/sdk/recorder";
import type { JsonValue } from "@agent-voyager-project/sdk/reports";
import * as translate from "./translate.js";
interface Message {
  session: string;
  info?: AssistantMessage;
  parts: Map<string, Part>;
  consumed: Set<string>;
}
interface Step {
  message: Message;
  finish?: StepFinishPart;
  parts: Part[];
}
export class EventClock {
  private timestamp?: number;
  now = (): Date => new Date(this.timestamp ?? Date.now());
  async at<T>(timestamp: number | undefined, fn: () => Promise<T>): Promise<T> {
    this.timestamp = timestamp;
    try {
      return await fn();
    } finally {
      this.timestamp = undefined;
    }
  }
}
export class SessionEvents {
  idle = false;
  failure?: unknown;
  private messages = new Map<string, Message>();
  private steps = new Map<string, Step[]>();
  private seen = new Set<string>();
  private scopes = new Map<string, string>();
  private pending = new Map<string, { part: ToolPart; parent?: string }>();
  private frames = new Set<string>();
  private last?: Message;
  constructor(
    private rec: Recorder,
    private clock: EventClock,
    readonly root: string,
    private subagents: Set<string>,
    private abort: () => Promise<unknown>,
  ) {}
  private message(id: string, session: string): Message {
    let m = this.messages.get(id);
    if (!m) {
      m = { session, parts: new Map(), consumed: new Set() };
      this.messages.set(id, m);
    }
    return m;
  }
  async handle(event: Event): Promise<void> {
    if (event.type === "message.updated") {
      const info = event.properties.info;
      if (info.role !== "assistant") return;
      const m = this.message(info.id, info.sessionID);
      m.info = info;
      if (m.session === this.root) this.last = m;
    } else if (event.type === "message.part.updated") {
      const part = event.properties.part,
        m = this.message(part.messageID, part.sessionID);
      m.parts.set(part.id, part);
      if (part.type === "compaction")
        throw new Error(
          "OpenCode compacted the run despite compaction being disabled",
        );
      if (part.type === "step-finish" && !this.seen.has(part.id)) {
        this.seen.add(part.id);
        const step = {
          message: m,
          finish: part,
          parts: [...m.parts.values()].filter((p) => !m.consumed.has(p.id)),
        };
        step.parts.forEach((p) => m.consumed.add(p.id));
        const list = this.steps.get(m.session) ?? [];
        list.push(step);
        this.steps.set(m.session, list);
        if (m.session === this.root || this.scopes.has(m.session))
          await this.flush(m.session);
      } else if (part.type === "tool" && this.pending.has(part.callID)) {
        const pending = this.pending.get(part.callID)!;
        pending.part = part;
        await this.attach(part, pending.parent);
        if (translate.completed(part))
          await this.returned(part, pending.parent);
      }
    } else if (event.type === "message.part.delta") {
      const p = event.properties;
      const part = this.messages.get(p.messageID)?.parts.get(p.partID);
      if (
        part &&
        (part.type === "text" || part.type === "reasoning") &&
        p.field === "text"
      )
        part.text += p.delta;
    } else if (event.type === "session.error") {
      if (
        (!event.properties.sessionID ||
          event.properties.sessionID === this.root) &&
        event.properties.error?.name !== "MessageAbortedError"
      )
        this.failure = event.properties.error;
    } else if (
      event.type === "session.status" &&
      event.properties.sessionID === this.root &&
      event.properties.status.type === "retry"
    ) {
      if (
        /quota|credits|billing|insufficient/i.test(
          event.properties.status.message,
        )
      ) {
        this.failure = event.properties.status.message;
        await this.abort();
      }
    } else if (
      event.type === "session.idle" &&
      event.properties.sessionID === this.root
    )
      this.idle = true;
  }
  async flushInterrupted(): Promise<void> {
    for (const message of this.messages.values()) {
      if (message.session !== this.root || !message.info || message.info.finish)
        continue;
      const parts = [...message.parts.values()].filter(
        (p) =>
          !message.consumed.has(p.id) &&
          (p.type !== "tool" || p.state.status !== "pending"),
      );
      parts.forEach((p) => message.consumed.add(p.id));
      if (parts.length) await this.report({ message, parts });
    }
  }
  private async flush(session: string): Promise<void> {
    const list = this.steps.get(session) ?? [];
    while (list.length) {
      const step = list.shift()!;
      await this.report(step, this.scopes.get(session));
    }
  }
  private async report(step: Step, parent?: string): Promise<void> {
    const info = step.message.info;
    if (!info)
      throw new Error("OpenCode completed a response without model metadata");
    const parts = step.parts
      .map((p) => ({ part: p, block: translate.block(p) }))
      .filter((p) => p.block !== undefined);
    const fallback = step.finish
      ? info.time.created
      : (info.time.completed ?? Date.now());
    const done = Math.max(
      info.time.created,
      ...parts.map((p) => translate.start(p.part) ?? fallback),
    );
    const options = {
      key: step.finish?.id ?? `aborted:${info.id}`,
      model: { provider: info.providerID, id: info.modelID },
      usage: step.finish ? translate.usage(step.finish) : undefined,
      finishReasons: [step.finish?.reason ?? "aborted"],
      durationMs: Math.max(0, done - info.time.created),
      subagentInvocationId: parent,
    };
    // Pin each call's own native start time; the Recorder then calculates tool
    // durations from native starts/ends even when parallel results arrive later.
    for (const p of parts)
      await this.clock.at(translate.start(p.part) ?? done, () =>
        this.rec.response([p.block!], options),
      );
    if (parts.length)
      await this.clock.at(done, () => this.rec.response([], options));
    await this.rec.closeResponse();
    const tools = step.parts.filter((p): p is ToolPart => p.type === "tool");
    for (const tool of tools) {
      this.pending.set(tool.callID, { part: tool, parent });
      await this.attach(tool, parent);
    }
    for (const tool of tools
      .filter(translate.completed)
      .sort((a, b) => (translate.end(a) ?? 0) - (translate.end(b) ?? 0)))
      await this.returned(tool, parent);
  }
  private async attach(tool: ToolPart, parent?: string): Promise<void> {
    if (tool.tool !== "task") return;
    const name = String(tool.state.input.subagent_type ?? "");
    if (!this.subagents.has(name)) return;
    if (!this.frames.has(tool.callID)) {
      await this.clock.at(translate.start(tool), () =>
        this.rec.subagentInvoked(
          tool.callID,
          name,
          tool.state.input as Record<string, JsonValue>,
          { subagentInvocationId: parent },
        ),
      );
      this.frames.add(tool.callID);
    }
    const child =
      "metadata" in tool.state ? tool.state.metadata?.sessionId : undefined;
    if (typeof child === "string") {
      this.scopes.set(child, tool.callID);
      await this.flush(child);
    }
  }
  private async returned(tool: ToolPart, _parent?: string): Promise<void> {
    if (!this.pending.delete(tool.callID)) return;
    const child =
      "metadata" in tool.state ? tool.state.metadata?.sessionId : undefined;
    let isError = tool.state.status === "error";
    if (this.frames.delete(tool.callID)) {
      const messages = [...this.messages.values()].filter(
        (m) => m.session === child,
      );
      const last = messages.at(-1);
      isError ||= !!last?.info?.error;
      const content = translate.result(tool);
      const text =
        this.text(last) ||
        (typeof content === "string"
          ? content
          : content
              .filter((b) => b.type === "text")
              .map((b) => b.text)
              .join(""));
      await this.clock.at(translate.end(tool), () =>
        this.rec.subagentReturned(
          tool.callID,
          text,
          isError ? "error" : "converged",
        ),
      );
    }
    await this.clock.at(translate.end(tool), () =>
      this.rec.toolReturned(tool.callID, translate.result(tool), { isError }),
    );
  }
  private text(m?: Message): string {
    return m
      ? [...m.parts.values()]
          .flatMap((p) =>
            p.type === "text" && !p.synthetic && !p.ignored ? [p.text] : [],
          )
          .join("")
      : "";
  }
  get output(): JsonValue | undefined {
    return (
      (this.last?.info?.structured as JsonValue | undefined) ??
      (this.text(this.last) || undefined)
    );
  }
  get lastError(): unknown {
    return this.last?.info?.error?.name === "MessageAbortedError"
      ? undefined
      : this.last?.info?.error;
  }
  check(): void {
    for (const [session, steps] of this.steps)
      if (steps.length && session !== this.root && !this.scopes.has(session))
        throw new Error(
          "OpenCode child responses could not be attributed to a task invocation",
        );
  }
}

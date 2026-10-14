/**
 * A scripted OpenAI Responses endpoint for the seam tests. Each `POST
 * /v1/responses` streams the next scripted step as Responses SSE, the shape
 * OpenCode's OpenAI SDK parses; a step can instead fail with an HTTP status.
 */
import { createServer, type IncomingMessage, type Server } from "node:http";
import type { AddressInfo } from "node:net";

export type Step =
  | { text: string; chunkDelayMs?: number }
  | { call: { id: string; name: string; args: Record<string, unknown> }; text?: string }
  | { status: number; body: Record<string, unknown> };

export interface Usage {
  input: number;
  cached: number;
  output: number;
}

export const USAGE: Usage = { input: 120, cached: 20, output: 30 };

export class ScriptedModel {
  /** Every request body received, in order. */
  readonly requests: Record<string, any>[] = [];
  private readonly server: Server;
  private steps: Step[] = [];

  private constructor(server: Server) {
    this.server = server;
  }

  static async start(): Promise<ScriptedModel> {
    const server = createServer();
    const model = new ScriptedModel(server);
    server.on("request", (req, res) => {
      void body(req).then((raw) => {
        if (req.method !== "POST" || !req.url?.endsWith("/responses")) {
          res.writeHead(404).end();
          return;
        }
        model.requests.push(JSON.parse(raw || "{}"));
        const step = model.steps.shift() ?? { text: "(no more scripted steps)" };
        if ("status" in step) {
          res.writeHead(step.status, { "content-type": "application/json" }).end(JSON.stringify(step.body));
          return;
        }
        res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
        void stream(res, step).catch(() => res.destroy());
      });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    return model;
  }

  get baseUrl(): string {
    return `http://127.0.0.1:${(this.server.address() as AddressInfo).port}/v1`;
  }

  script(steps: Step[]): void {
    this.steps = [...steps];
    this.requests.length = 0;
  }

  async close(): Promise<void> {
    this.server.closeAllConnections();
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }
}

async function stream(res: import("node:http").ServerResponse, step: Exclude<Step, { status: number }>): Promise<void> {
  let seq = 0;
  const send = (data: Record<string, unknown>) =>
    new Promise<void>((resolve) => res.write(`data: ${JSON.stringify({ ...data, sequence_number: seq++ })}\n\n`, () => resolve()));
  const id = `resp_${Math.random().toString(36).slice(2)}`;
  await send({ type: "response.created", response: { id, created_at: Math.floor(Date.now() / 1000), model: "gpt-4.1-2025-04-14" } });
  let index = 0;
  const text = "text" in step ? step.text : undefined;
  if (text) {
    const item = `msg_${index}`;
    await send({ type: "response.output_item.added", output_index: index, item: { type: "message", id: item } });
    const delay = "chunkDelayMs" in step ? step.chunkDelayMs : undefined;
    for (const word of delay ? text.match(/\S+\s*/g) ?? [text] : [text]) {
      if (res.destroyed) return;
      await send({ type: "response.output_text.delta", item_id: item, delta: word });
      if (delay) await new Promise((r) => setTimeout(r, delay));
    }
    await send({ type: "response.output_item.done", output_index: index, item: { type: "message", id: item } });
    index++;
  }
  if ("call" in step) {
    const { id: callId, name, args } = step.call;
    const item = `fc_${index}`;
    const json = JSON.stringify(args);
    await send({
      type: "response.output_item.added",
      output_index: index,
      item: { type: "function_call", id: item, call_id: callId, name, arguments: "" },
    });
    await send({ type: "response.function_call_arguments.delta", item_id: item, output_index: index, delta: json });
    await send({
      type: "response.output_item.done",
      output_index: index,
      item: { type: "function_call", id: item, call_id: callId, name, arguments: json, status: "completed" },
    });
  }
  await send({
    type: "response.completed",
    response: {
      incomplete_details: null,
      usage: {
        input_tokens: USAGE.input,
        input_tokens_details: { cached_tokens: USAGE.cached },
        output_tokens: USAGE.output,
        output_tokens_details: { reasoning_tokens: 0 },
      },
    },
  });
  res.end();
}

function body(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk: Buffer) => (raw += chunk.toString()));
    req.on("end", () => resolve(raw));
  });
}

/** Per-response native parts and reported costs become SDK reports. */
import type {
  Part,
  StepFinishPart,
  ToolPart,
} from "@opencode-ai/sdk/v2/client";
import type {
  ContentBlock,
  ErrorCode,
  ToolResultBlock,
  ImageBlock,
  TextBlock,
} from "@agent-voyager-project/sdk/reports";
import type { UsageReport } from "@agent-voyager-project/sdk/recorder";
export function usage(finish: StepFinishPart): UsageReport {
  const t = finish.tokens;
  return {
    input_tokens: t.input + t.cache.read + t.cache.write,
    output_tokens: t.output + t.reasoning,
    cache_read_input_tokens: t.cache.read,
    cache_creation_input_tokens: t.cache.write,
    reasoning_output_tokens: t.reasoning,
    cost_usd: finish.cost,
  };
}
export function block(part: Part): ContentBlock | undefined {
  if (part.type === "text")
    return part.synthetic || part.ignored
      ? undefined
      : { type: "text", text: part.text };
  if (part.type === "reasoning")
    return { type: "thinking", thinking: part.text };
  if (part.type === "tool") {
    if (part.tool === "invalid")
      throw new Error(
        "OpenCode's repair tool obscures the model's original tool call",
      );
    return {
      type: "tool_use",
      id: part.callID,
      name: part.tool,
      input: part.state.input as Record<string, never>,
    };
  }
  if (part.type === "file")
    throw new Error(
      "OpenCode model file content is not exposed as AVP content by this adapter",
    );
  if (part.type === "compaction")
    throw new Error(
      "OpenCode context compaction cannot be recorded by this adapter",
    );
}
export function completed(part: ToolPart): boolean {
  return part.state.status === "completed" || part.state.status === "error";
}
export function result(part: ToolPart): ToolResultBlock["content"] {
  if (part.state.status === "error") return part.state.error;
  if (part.state.status !== "completed")
    throw new Error("OpenCode tool has not returned");
  const content: (TextBlock | ImageBlock)[] = [
    { type: "text", text: part.state.output },
  ];
  for (const file of part.state.attachments ?? []) {
    if (!file.mime.startsWith("image/"))
      throw new Error(`unsupported OpenCode tool attachment: ${file.mime}`);
    const embedded = file.url.match(/^data:([^;,]+);base64,(.*)$/s);
    if (embedded)
      content.push({
        type: "image",
        source: {
          type: "base64",
          media_type: embedded[1]!,
          data: embedded[2]!,
        },
      });
    else throw new Error(`unsupported OpenCode image location`);
  }
  return content;
}
export function start(part: Part): number | undefined {
  return part.type === "tool" && "time" in part.state
    ? part.state.time.start
    : part.type === "text" || part.type === "reasoning"
      ? part.time?.end
      : undefined;
}
export function end(part: ToolPart): number | undefined {
  return "time" in part.state && "end" in part.state.time
    ? part.state.time.end
    : undefined;
}
export function errorText(error: unknown): string {
  if (error && typeof error === "object" && "data" in error)
    return String(
      (error.data as { message?: string })?.message ?? JSON.stringify(error),
    );
  return error instanceof Error ? error.message : String(error);
}
export function errorCode(error: unknown): ErrorCode {
  const text = typeof error === "string" ? error : JSON.stringify(error);
  if (
    /401|403|ProviderAuthError|api.?key.*(invalid|not valid|missing)|unauth|authentication/i.test(
      text,
    )
  )
    return "auth_error";
  if (/429|rate.limit|quota|credits|billing/i.test(text)) return "rate_limit";
  if (/ContextOverflowError|context.{0,20}(long|limit)|token limit/i.test(text))
    return "context_limit";
  return "unknown";
}

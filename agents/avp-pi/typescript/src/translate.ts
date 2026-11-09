/** Native Pi responses use deltas; cache reads and writes are outside input. */
import type {
  AssistantMessage,
  ToolResultMessage,
  Usage,
} from "@earendil-works/pi-ai";
import type {
  ContentBlock,
  ErrorCode,
  ImageBlock,
  TextBlock,
} from "@agent-voyager-project/sdk/reports";
import type { UsageReport } from "@agent-voyager-project/sdk/recorder";

type PiBlock =
  AssistantMessage["content"][number] | ToolResultMessage["content"][number];

export function content(blocks: readonly PiBlock[]): ContentBlock[] {
  return blocks.map((b) => {
    switch (b.type) {
      case "text":
        return { type: "text", text: b.text };
      case "thinking":
        return {
          type: "thinking",
          thinking: b.thinking,
          ...(b.thinkingSignature ? { signature: b.thinkingSignature } : {}),
          ...(b.redacted ? { redacted: true } : {}),
        };
      case "toolCall":
        return { type: "tool_use", id: b.id, name: b.name, input: b.arguments };
      case "image":
        return {
          type: "image",
          source: { type: "base64", media_type: b.mimeType, data: b.data },
        };
      default:
        throw new TypeError(`unsupported Pi content: ${JSON.stringify(b)}`);
    }
  });
}

export function toolContent(
  blocks: ToolResultMessage["content"],
): (TextBlock | ImageBlock)[] {
  return content(blocks) as (TextBlock | ImageBlock)[];
}

export function usage(u: Usage): UsageReport {
  return {
    input_tokens: u.input + u.cacheRead + u.cacheWrite,
    output_tokens: u.output,
    cache_read_input_tokens: u.cacheRead,
    cache_creation_input_tokens: u.cacheWrite,
    ...(u.reasoning === undefined
      ? {}
      : { reasoning_output_tokens: u.reasoning }),
  };
}

export function errorCode(error: unknown): ErrorCode {
  const message = error instanceof Error ? error.message : String(error);
  if (
    /\b401\b|\b403\b|unauthori[sz]ed|authentication|invalid[ _-]?api[ _-]?key|no api key/i.test(
      message,
    )
  )
    return "auth_error";
  if (
    /\b429\b|rate[ _-]?limit|too many requests|quota|overloaded/i.test(message)
  )
    return "rate_limit";
  if (/context|too long|maximum.*tokens|token limit/i.test(message))
    return "context_limit";
  return "agent_crash";
}

/** Native Pi responses use deltas; cache reads and writes are outside input. */
import type {
  AssistantMessage,
  ToolResultMessage,
  Usage as PiUsage,
} from "@earendil-works/pi-ai";
import type { Part, Image, Text } from "@agent-voyager-project/sdk/recorder";
import type { Usage, Recorder } from "@agent-voyager-project/sdk/recorder";
import type { ErrorCode } from "@agent-voyager-project/sdk/trajectory";

type PiBlock =
  AssistantMessage["content"][number] | ToolResultMessage["content"][number];

export function parts(blocks: readonly PiBlock[], rec: Recorder): Part[] {
  return blocks.map((b) => {
    switch (b.type) {
      case "text":
        return { type: "text", text: b.text };
      case "thinking":
        return {
          type: "reasoning",
          ...(b.redacted
            ? { encrypted_content: b.thinking }
            : { text: b.thinking }),
          ...(b.thinkingSignature ? { signature: b.thinkingSignature } : {}),
        };
      case "toolCall":
        return { type: "call", id: b.id, name: b.name, arguments: b.arguments };
      case "image":
        return rec.imageBase64(b.data, b.mimeType);
      default:
        throw new TypeError(`unsupported Pi content: ${JSON.stringify(b)}`);
    }
  });
}

export function toolContent(
  blocks: ToolResultMessage["content"],
  rec: Recorder,
): (Text | Image)[] {
  return parts(blocks, rec) as (Text | Image)[];
}

export function usage(u: PiUsage): Usage {
  return {
    prompt_tokens: u.input + u.cacheRead + u.cacheWrite,
    completion_tokens: u.output,
    cached_tokens: u.cacheRead,
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

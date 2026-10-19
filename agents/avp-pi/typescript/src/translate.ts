/**
 * Pi values -> AVP wire values.
 *
 * Pi's `Usage.input` excludes cache reads and writes (they are reported
 * separately and `totalTokens` is their sum); AVP's `input_tokens` includes
 * them. Pi's `reasoning` is already part of `output`.
 */
import type { ContentBlock } from "@avp/types";
import type { ErrorCode, Usage } from "@avp/types/trajectory";
import type { AssistantMessage, ToolResultMessage, Usage as PiUsage } from "@earendil-works/pi-ai";

type PiBlock = AssistantMessage["content"][number] | ToolResultMessage["content"][number];

/** One Pi content block as an AVP block; unknown kinds are dropped. */
export function block(b: PiBlock): ContentBlock | undefined {
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
      return { type: "tool_use", id: b.id, name: b.name, input: b.arguments ?? {} };
    case "image":
      return { type: "image", source: { type: "base64", media_type: b.mimeType, data: b.data } };
    default:
      return undefined;
  }
}

export function content(blocks: readonly PiBlock[]): ContentBlock[] {
  return blocks.map(block).filter((b): b is ContentBlock => b !== undefined);
}

export function usage(u: PiUsage): Usage {
  return {
    input_tokens: u.input + u.cacheRead + u.cacheWrite,
    output_tokens: u.output,
    cache_read_input_tokens: u.cacheRead,
    cache_creation_input_tokens: u.cacheWrite,
    ...(u.reasoning ? { reasoning_output_tokens: u.reasoning } : {}),
  };
}

/** Pi's terminal stop reason, and the provider's raw one when it differs. */
export function finishReasons(m: AssistantMessage): string[] {
  return m.rawStopReason && m.rawStopReason !== m.stopReason ? [m.stopReason, m.rawStopReason] : [m.stopReason];
}

/** Classify a provider failure Pi reports as an assistant `errorMessage`. */
export function errorCode(message: string): ErrorCode {
  if (/\b401\b|\b403\b|unauthori[sz]ed|authentication|invalid[ _-]?api[ _-]?key|no api key/i.test(message)) {
    return "auth_error";
  }
  if (/\b429\b|rate[ _-]?limit|too many requests|quota|overloaded/i.test(message)) return "rate_limit";
  if (/context|too long|maximum.*tokens|token limit/i.test(message)) return "context_limit";
  return "unknown";
}

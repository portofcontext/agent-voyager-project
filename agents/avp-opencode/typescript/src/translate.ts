/**
 * OpenCode values -> AVP wire values.
 *
 * A `step-finish` part's tokens split the AI SDK's usage: `input` excludes
 * cache reads and writes, and `output` excludes `reasoning`. AVP's
 * `input_tokens` includes the cache split and `output_tokens` includes
 * reasoning, so both are added back.
 */
import type { ContentBlock } from "@avp/types";
import type { ErrorCode, Usage } from "@avp/types/trajectory";
import type { AssistantMessage, Part, StepFinishPart } from "@opencode-ai/sdk/v2/client";

export type OpencodeError = NonNullable<AssistantMessage["error"]>;

export function usage(tokens: StepFinishPart["tokens"]): Usage {
  return {
    input_tokens: tokens.input + tokens.cache.read + tokens.cache.write,
    output_tokens: tokens.output + tokens.reasoning,
    cache_read_input_tokens: tokens.cache.read,
    cache_creation_input_tokens: tokens.cache.write,
    ...(tokens.reasoning ? { reasoning_output_tokens: tokens.reasoning } : {}),
  };
}

/**
 * One OpenCode part as an AVP block: text, reasoning, and tool calls (under
 * `toolName`'s AVP name). Step markers, patches, and the rest carry no model
 * output and are dropped.
 */
export function block(part: Part, toolName: (opencodeName: string) => string): ContentBlock | undefined {
  switch (part.type) {
    case "text":
      return part.synthetic || part.ignored || !part.text ? undefined : { type: "text", text: part.text };
    case "reasoning":
      return part.text ? { type: "thinking", thinking: part.text } : undefined;
    case "tool":
      return { type: "tool_use", id: part.callID, name: toolName(part.tool), input: part.state.input ?? {} };
    default:
      return undefined;
  }
}

/** A finished tool part's result text, or undefined while it is still pending or running. */
export function toolResult(part: Part): { text: string; isError: boolean } | undefined {
  if (part.type !== "tool") return undefined;
  if (part.state.status === "completed") return { text: part.state.output, isError: false };
  if (part.state.status === "error") return { text: part.state.error, isError: true };
  return undefined;
}

/** A provider failure OpenCode recorded on a message or session. */
export function errorCode(error: OpencodeError | { name: string; data?: unknown }): ErrorCode {
  const data = (error.data ?? {}) as { message?: string; statusCode?: number; responseBody?: string };
  switch (error.name) {
    case "ProviderAuthError":
      return "auth_error";
    case "ContextOverflowError":
      return "context_limit";
    case "APIError":
      if (data.statusCode === 401 || data.statusCode === 403) return "auth_error";
      if (data.statusCode === 429) return "rate_limit";
      if (data.statusCode === 413) return "context_limit";
      return messageCode(`${data.message ?? ""} ${data.responseBody ?? ""}`);
    default:
      return messageCode(data.message ?? "");
  }
}

/** Classify a provider failure by its message. */
export function messageCode(message: string): ErrorCode {
  if (/\b401\b|\b403\b|unauthori[sz]ed|authentication|invalid[ _-]?api[ _-]?key|incorrect api key|api[ _-]?key not valid/i.test(message)) {
    return "auth_error";
  }
  if (/\b429\b|rate[ _-]?limit|too many requests|quota|credits|billing/i.test(message)) return "rate_limit";
  if (/context|too long|maximum.*tokens|token limit/i.test(message)) return "context_limit";
  return "unknown";
}

/** A retry OpenCode would keep making in vain: the account is out of quota or credit. */
export function hopelessRetry(message: string): boolean {
  return /quota|credits|billing|insufficient/i.test(message);
}

export function errorMessage(error: OpencodeError | { name: string; data?: unknown }): string {
  const data = (error.data ?? {}) as { message?: string };
  return data.message || error.name;
}

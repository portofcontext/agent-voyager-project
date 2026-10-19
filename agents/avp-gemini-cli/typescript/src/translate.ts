/**
 * Gemini CLI values -> AVP wire values.
 *
 * Gemini's `promptTokenCount` already includes `cachedContentTokenCount`, as
 * AVP's `input_tokens` includes cache reads; tool-use prompt tokens are input
 * too. `candidatesTokenCount` excludes `thoughtsTokenCount`, while AVP's
 * `output_tokens` includes reasoning, so thoughts are added to output and
 * reported as `reasoning_output_tokens` as well. The Gemini API has no
 * cache-write charge.
 */
import type { ContentBlock } from "@avp/types";
import type { ErrorCode, Usage } from "@avp/types/trajectory";
import type { Part } from "@google/gemini-cli-core";

/** The `usageMetadata` fields Gemini returns on a response. */
export interface GeminiUsage {
  promptTokenCount?: number;
  cachedContentTokenCount?: number;
  candidatesTokenCount?: number;
  thoughtsTokenCount?: number;
  toolUsePromptTokenCount?: number;
}

export function usage(u: GeminiUsage | undefined): Usage {
  const thoughts = u?.thoughtsTokenCount ?? 0;
  return {
    input_tokens: (u?.promptTokenCount ?? 0) + (u?.toolUsePromptTokenCount ?? 0),
    output_tokens: (u?.candidatesTokenCount ?? 0) + thoughts,
    cache_read_input_tokens: u?.cachedContentTokenCount ?? 0,
    ...(thoughts ? { reasoning_output_tokens: thoughts } : {}),
  };
}

/**
 * A thought summary as Gemini CLI parses it (`**subject** description`) back
 * into one thinking text.
 */
export function thoughtText(subject: string, description: string): string {
  return subject ? `**${subject}**${description ? `\n${description}` : ""}` : description;
}

/**
 * The model-facing parts of a tool response as AVP blocks: a function
 * response's `output` (or `error`) text, otherwise its JSON; inline images
 * as image blocks.
 */
export function toolResultContent(parts: readonly Part[]): ContentBlock[] {
  const out: ContentBlock[] = [];
  for (const part of parts) {
    if (part.functionResponse) {
      const response = part.functionResponse.response ?? {};
      const text = typeof response["output"] === "string"
        ? response["output"]
        : typeof response["error"] === "string"
          ? response["error"]
          : JSON.stringify(response);
      out.push({ type: "text", text });
      for (const inner of part.functionResponse.parts ?? []) {
        const data = inner.inlineData;
        if (data?.data && data.mimeType?.startsWith("image/")) {
          out.push({ type: "image", source: { type: "base64", media_type: data.mimeType, data: data.data } });
        }
      }
    } else if (part.text !== undefined) {
      out.push({ type: "text", text: part.text });
    } else if (part.inlineData?.data && part.inlineData.mimeType?.startsWith("image/")) {
      out.push({
        type: "image",
        source: { type: "base64", media_type: part.inlineData.mimeType, data: part.inlineData.data },
      });
    }
  }
  return out;
}

/** Classify a provider failure from its message and HTTP status. */
export function errorCode(message: string, status?: number): ErrorCode {
  if (
    status === 401 ||
    status === 403 ||
    /api[ _-]?key not valid|invalid[ _-]?api[ _-]?key|api_key_invalid|unauthenticated|unauthori[sz]ed|permission denied|no api key|api key (is )?(missing|must be set)/i.test(
      message,
    )
  ) {
    return "auth_error";
  }
  if (status === 429 || /\b429\b|rate[ _-]?limit|resource[ _-]?exhausted|quota|too many requests/i.test(message)) {
    return "rate_limit";
  }
  if (/context window|exceeds the maximum number of tokens|input token count|too long|token limit/i.test(message)) {
    return "context_limit";
  }
  if (status === 404 || /\bmodels\/\S+ is not found|model .*not found|not supported for generatecontent/i.test(message)) {
    return "unsupported_model";
  }
  return "unknown";
}

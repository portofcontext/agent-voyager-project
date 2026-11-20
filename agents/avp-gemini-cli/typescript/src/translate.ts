/** Translate per-response native values; cache is input and reasoning is output. */
import type { Part as NativePart } from "@google/gemini-cli-core";
import type { Part, Text, Image } from "@agent-voyager-project/sdk/recorder";
import type { Usage, Recorder } from "@agent-voyager-project/sdk/recorder";
import type { ErrorCode } from "@agent-voyager-project/sdk/trajectory";
export interface GeminiUsage {
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  cachedContentTokenCount?: number;
  thoughtsTokenCount?: number;
  toolUsePromptTokenCount?: number;
}
export function usage(value?: GeminiUsage): Usage {
  if (!value || value.promptTokenCount === undefined)
    throw new Error("Gemini response has no input usage metadata");
  return {
    prompt_tokens:
      value.promptTokenCount + (value.toolUsePromptTokenCount ?? 0),
    completion_tokens:
      (value.candidatesTokenCount ?? 0) + (value.thoughtsTokenCount ?? 0),
    cached_tokens: value.cachedContentTokenCount ?? 0,
    ...(value.thoughtsTokenCount == null
      ? {}
      : { reasoning_output_tokens: value.thoughtsTokenCount }),
  };
}
export function toolContent(
  parts: readonly NativePart[],
  rec: Recorder,
): (Text | Image)[] {
  const out: (Text | Image)[] = [];
  for (const p of parts) {
    if (p.functionResponse) {
      const response = p.functionResponse.response ?? {};
      out.push({
        type: "text",
        text:
          typeof response.output === "string"
            ? response.output
            : typeof response.error === "string"
              ? response.error
              : JSON.stringify(response),
      });
      for (const inner of p.functionResponse.parts ?? []) {
        const d = inner.inlineData;
        if (d?.data && d.mimeType?.startsWith("image/"))
          out.push(rec.imageBase64(d.data, d.mimeType));
        else throw new Error("unsupported Gemini function response content");
      }
    } else if (p.text !== undefined) out.push({ type: "text", text: p.text });
    else if (p.inlineData?.data && p.inlineData.mimeType?.startsWith("image/"))
      out.push(rec.imageBase64(p.inlineData.data, p.inlineData.mimeType));
    else throw new Error("unsupported Gemini tool content");
  }
  return out;
}
export function append(content: Part[], block: Part): void {
  const last = content.at(-1);
  if (last?.type === "text" && block.type === "text") last.text += block.text;
  else if (last?.type === "reasoning" && block.type === "reasoning")
    last.text = `${last.text ?? ""}\n${block.text ?? ""}`;
  else content.push(block);
}
export function errorCode(error: unknown): ErrorCode {
  const text = error instanceof Error ? error.message : String(error);
  if (
    /\b401\b|\b403\b|api.?key.*(invalid|not valid|missing|must)|unauth|permission denied|no api key/i.test(
      text,
    )
  )
    return "auth_error";
  if (/\b429\b|quota|resource.exhausted|rate.limit/i.test(text))
    return "rate_limit";
  if (/context window|token limit|too long|input token count/i.test(text))
    return "context_limit";
  return "unknown";
}

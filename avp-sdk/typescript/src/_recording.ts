/** Content mapping and subtree accounting for native ATIF recording. */
import { createHash } from "node:crypto";
export function metadata(value: any): any {
  return ((value.extra ??= {}).avp ??= {});
}
export function remaining(value: any, keys: string[]): any {
  return Object.fromEntries(
    Object.entries(value).filter(([k]) => !keys.includes(k)),
  );
}
export function modelMetadata(model: any): any {
  return {
    provider: model.provider,
    ...(model.base_url ? { base_url: model.base_url } : {}),
  };
}
export function contentMetadata(value: any): any[] {
  if (!Array.isArray(value)) return [];
  const out: any[] = [];
  for (const [i, block] of value.entries()) {
    let details: any;
    if (block?.type === "text") details = remaining(block, ["type", "text"]);
    else if (block?.type === "refusal")
      details = { ...remaining(block, ["type", "refusal"]), refusal: true };
    else if (block?.type === "image" && block.source?.type === "base64") {
      details = remaining(block, ["type", "source"]);
      const extra = remaining(block.source, ["type", "media_type", "data"]);
      if (Object.keys(extra).length) details.source = extra;
    } else return [];
    if (Object.keys(details).length)
      out.push({ part_index: i, annotations: details });
  }
  return out;
}
export function content(value: any, assets: Map<string, Uint8Array>): any {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return JSON.stringify(value);
  const parts: any[] = [];
  for (const block of value) {
    if (block?.type === "text") parts.push({ type: "text", text: block.text });
    else if (block?.type === "refusal")
      parts.push({ type: "text", text: block.refusal });
    else if (block?.type === "image" && block.source?.type === "base64") {
      const source = block.source;
      const ext: Record<string, string> = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
      };
      if (!ext[source.media_type])
        throw new TypeError(
          `ATIF does not support image media type ${source.media_type}`,
        );
      if (
        !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
          source.data,
        )
      )
        throw new TypeError("invalid base64 image");
      const bytes = Buffer.from(source.data, "base64");
      const path = `images/${createHash("sha256").update(bytes).digest("hex")}.${ext[source.media_type]}`;
      assets.set(path, bytes);
      parts.push({
        type: "image",
        source: { media_type: source.media_type, path },
      });
    } else return JSON.stringify(value);
  }
  return !parts.length
    ? ""
    : parts.length === 1 && parts[0].type === "text"
      ? parts[0].text
      : parts;
}
export function metrics(usage: any): any {
  const out: any = {};
  for (const [source, target] of [
    ["input_tokens", "prompt_tokens"],
    ["output_tokens", "completion_tokens"],
    ["cache_read_input_tokens", "cached_tokens"],
  ])
    if (usage[source] != null) out[target] = usage[source];
  if (usage.cost_usd != null && usage.cost_source !== "unknown")
    out.cost_usd = usage.cost_usd;
  const extra = remaining(usage, [
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cost_usd",
  ]);
  if (Object.keys(extra).length) out.extra = { avp: extra };
  return out;
}
export class Document {
  usages: any[] = [];
  children: Document[] = [];
  data: any;
  constructor(run: string, id: string, name: string, version: string) {
    this.data = {
      schema_version: "ATIF-v1.8",
      session_id: run,
      trajectory_id: id,
      agent: { name, version },
      steps: [],
      extra: { avp: { complete: false } },
      notes:
        "Usage totals include descendants once; total_steps counts this document's steps only. Missing metrics are unknown. Unrecorded context is not reconstructed.",
    };
  }
  step(timestamp: string, source: string, message: any): any {
    const step = {
      step_id: this.data.steps.length + 1,
      timestamp,
      source,
      message,
    };
    this.data.steps.push(step);
    return step;
  }
  finish(): any[] {
    const usages = [
      ...this.usages,
      ...this.children.flatMap((c) => c.finish()),
    ];
    const totals: any = { total_steps: this.data.steps.length },
      known: any = {};
    for (const [source, target] of [
      ["input_tokens", "total_prompt_tokens"],
      ["output_tokens", "total_completion_tokens"],
      ["cache_read_input_tokens", "total_cached_tokens"],
      ["cost_usd", "total_cost_usd"],
    ]) {
      const measured = usages.filter(
        (u) =>
          u[source] != null &&
          !(source === "cost_usd" && u.cost_source === "unknown"),
      );
      (measured.length === usages.length ? totals : known)[target] =
        measured.reduce((n, u) => n + u[source], 0);
    }
    totals.extra = { avp: { usage_scope: "subtree", known_totals: known } };
    this.data.final_metrics = totals;
    return usages;
  }
}
export function observation(step: any, callId?: string): any {
  const results = (step.observation ??= { results: [] }).results;
  let result = results.find((r: any) => r.source_call_id === callId);
  if (!result) {
    result = callId ? { source_call_id: callId } : {};
    results.push(result);
  }
  return result;
}

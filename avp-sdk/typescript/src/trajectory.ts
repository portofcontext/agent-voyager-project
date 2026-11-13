/** ATIF documents. Accepts upstream producers without AVP extensions. */
import { readFileSync } from "node:fs";
import type { ArtifactFile } from "./artifacts.js";
import { ajv } from "./validation.js";
import type { Trajectory } from "./wire.js";
export type {
  Trajectory,
  Step,
  Metrics,
  FinalMetrics,
  Observation,
  ObservationResult,
  ToolCall,
  ContentPart,
} from "./wire.js";
export interface Recording {
  trajectory: Trajectory;
  assets: Map<string, Uint8Array>;
  artifacts?: Map<string, ArtifactFile>;
}
export type TrajectorySink = (snapshot: Recording) => Promise<void>;
const schema = JSON.parse(
  readFileSync(new URL("./schemas/trajectory.json", import.meta.url), "utf8"),
);
const validate = ajv.compile(schema);
export function parseTrajectory(received: unknown): Trajectory {
  const value =
    typeof received === "string"
      ? JSON.parse(received)
      : structuredClone(received);
  // Match the upstream AudioSource normalizer before schema validation.
  const audioAliases: Record<string, string> = {
    "audio/mp3": "audio/mpeg",
    "audio/mpga": "audio/mpeg",
    "audio/x-mpeg": "audio/mpeg",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "audio/x-aac": "audio/aac",
    "audio/x-flac": "audio/flac",
    "audio/x-aiff": "audio/aiff",
  };
  function normalize(doc: any): void {
    for (const step of doc?.steps ?? []) {
      for (const content of [
        step.message,
        ...(step.observation?.results ?? []).map((r: any) => r.content),
      ]) {
        if (!Array.isArray(content)) continue;
        for (const part of content)
          if (
            typeof part?.source?.media_type === "string" &&
            part.source.media_type.trim().toLowerCase().startsWith("audio/")
          ) {
            const media = part.source.media_type.trim().toLowerCase();
            part.source.media_type = audioAliases[media] ?? media;
          }
      }
    }
    for (const child of doc?.subagent_trajectories ?? []) normalize(child);
  }
  normalize(value);
  if (!validate(value)) throw new TypeError(ajv.errorsText(validate.errors));
  function check(doc: any): void {
    const children = new Set<string>();
    for (const child of doc.subagent_trajectories ?? []) {
      if (child.trajectory_id == null || children.has(child.trajectory_id))
        throw new TypeError("embedded trajectories need unique IDs");
      children.add(child.trajectory_id);
      check(child);
    }
    for (const [i, step] of doc.steps.entries()) {
      if (step.step_id !== i + 1)
        throw new TypeError("step IDs must be sequential from 1");
      if (
        step.timestamp != null &&
        (!/^\d{4}-?\d{2}-?\d{2}/.test(step.timestamp) ||
          Number.isNaN(Date.parse(step.timestamp)))
      )
        throw new TypeError("invalid ISO 8601 timestamp");
      if (
        step.source !== "agent" &&
        [
          "model_name",
          "reasoning_effort",
          "reasoning_content",
          "tool_calls",
          "metrics",
        ].some((key) => step[key] != null)
      )
        throw new TypeError("model fields require an agent step");
      if (
        step.source === "agent" &&
        step.llm_call_count === 0 &&
        (step.metrics != null || step.reasoning_content != null)
      )
        throw new TypeError(
          "deterministic steps cannot carry LLM metrics or reasoning",
        );
      for (const content of [
        step.message,
        ...(step.observation?.results ?? []).map((r: any) => r.content),
      ]) {
        if (!Array.isArray(content)) continue;
        for (const part of content) {
          if (
            part.type === "text"
              ? part.text == null || part.source != null
              : part.source == null ||
                part.text != null ||
                !part.source.media_type.startsWith(`${part.type}/`)
          )
            throw new TypeError("content fields must match the part type");
        }
      }
      const calls = new Set(
        (step.tool_calls ?? []).map((c: any) => c.tool_call_id),
      );
      for (const result of step.observation?.results ?? []) {
        if (result.source_call_id != null && !calls.has(result.source_call_id))
          throw new TypeError("unmatched observation call ID");
        for (const ref of result.subagent_trajectory_ref ?? [])
          if (ref.trajectory_path == null && ref.trajectory_id == null)
            throw new TypeError("subagent references require an ID or path");
      }
    }
  }
  check(value);
  return structuredClone(value) as Trajectory;
}
export function* documents(root: Trajectory): Generator<Trajectory> {
  yield root;
  for (const child of root.subagent_trajectories ?? []) yield* documents(child);
}
export function avpMetadata(value: {
  extra?: Record<string, any> | null;
}): Record<string, any> {
  return value.extra?.avp ?? {};
}

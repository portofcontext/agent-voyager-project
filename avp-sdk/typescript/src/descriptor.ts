import { parseDefinition } from "./validation.js";
import type { AgentDescriptor } from "./wire.js";
export type {
  AgentDescriptor,
  DescriptorSkill as Skill,
  McpServer,
  ModelPattern,
  Subagent,
  Tool,
} from "./wire.js";

export function parseDescriptor(value: unknown): AgentDescriptor {
  return parseDefinition("AgentDescriptor", value);
}

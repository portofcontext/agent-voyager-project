import { parseDefinition } from "./validation.js";
import type { Commission } from "./wire.js";
export type {
  AgentSettings,
  Commission,
  CommissionSkill as Skill,
  EnvSecret,
  Model,
  ProxySecret,
  Supervisor,
  McpServerHttp,
  McpServerStdio,
} from "./wire.js";
export type McpServer = NonNullable<Commission["mcp_servers"]>[number];
export type SecretRef = NonNullable<Commission["model"]["credential"]>;

export function parseCommission(value: unknown): Commission {
  return parseDefinition("Commission", value);
}

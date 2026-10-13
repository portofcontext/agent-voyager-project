/**
 * The Commission checks every agent runs before its first turn.
 *
 * The spec requires an agent to refuse a Commission it can't honor before any
 * model turn, with `error_occurred` + `agent_stopped(error)`:
 *
 * - `agent_versions` pins this agent at a different build
 *   (`unsupported_agent_version`);
 * - an `enabled_builtin_*` allow-list map has no entry under this agent's name
 *   (`commission_collision`);
 * - an allow-list names a tool / subagent / skill / MCP server the agent
 *   doesn't offer (`commission_collision`).
 *
 * Fill in the surfaces the agent offers in `Offered`; a surface left
 * undefined is not checked by name. Harness-specific refusals stay in the
 * adapter. Matches the Python `avp.preflight` and the Rust `avp::preflight`.
 */
import type { Commission } from "./index.js";
import type { ErrorCode } from "./trajectory.js";

/** The names the agent offers per surface; undefined skips the by-name check. */
export interface Offered {
  tools?: readonly string[];
  subagents?: readonly string[];
  skills?: readonly string[];
  mcpServers?: readonly string[];
}

/** The first Commission check that fails, as `[code, message]`, or undefined. */
export function preflight(
  commission: Commission,
  agentName: string,
  agentVersion: string,
  offered: Offered = {},
): [ErrorCode, string] | undefined {
  const pin = commission.agent_versions?.[agentName];
  if (pin !== undefined && pin !== agentVersion) {
    return [
      "unsupported_agent_version",
      `Commission pins ${JSON.stringify(agentName)} at ${JSON.stringify(pin)}; this build is ${JSON.stringify(agentVersion)}`,
    ];
  }
  const lists: [string, Record<string, string[]> | null | undefined, readonly string[] | undefined][] = [
    ["enabled_builtin_tools", commission.enabled_builtin_tools, offered.tools],
    ["enabled_builtin_subagents", commission.enabled_builtin_subagents, offered.subagents],
    ["enabled_builtin_skills", commission.enabled_builtin_skills, offered.skills],
    ["enabled_builtin_mcp_servers", commission.enabled_builtin_mcp_servers, offered.mcpServers],
  ];
  const missing = lists
    .filter(([, map]) => map != null && !Object.hasOwn(map, agentName))
    .map(([field]) => field);
  if (missing.length > 0) {
    return ["commission_collision", `no ${JSON.stringify(agentName)} entry in: ${missing.join(", ")}`];
  }
  for (const [field, map, names] of lists) {
    const allowed = map?.[agentName];
    if (!allowed || !names) continue;
    const unknown = allowed.filter((n) => !names.includes(n));
    if (unknown.length > 0) {
      return ["commission_collision", `${field} names not offered by the agent: ${unknown.join(", ")}`];
    }
  }
  return undefined;
}

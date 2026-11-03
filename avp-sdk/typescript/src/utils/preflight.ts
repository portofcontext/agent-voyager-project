import type { Commission } from "../commission.js";
import type { AgentDescriptor } from "../descriptor.js";
import { frontmatterValue, repr } from "./skill_md.js";

export function checkAgentEntry(
  commission: Commission,
  descriptor: AgentDescriptor,
): string | undefined {
  if (
    commission.agents != null &&
    !Object.hasOwn(commission.agents, descriptor.agent_name)
  )
    return `agents has no entry for ${repr(descriptor.agent_name)}`;
}
export function checkAgentVersion(
  commission: Commission,
  descriptor: AgentDescriptor,
): string | undefined {
  const version = commission.agents?.[descriptor.agent_name]?.version;
  if (version != null && version !== descriptor.agent_version)
    return `agents.${descriptor.agent_name}.version is ${repr(version)}, but this agent is version ${repr(descriptor.agent_version)}`;
}
export function checkEnabledItems(
  commission: Commission,
  descriptor: AgentDescriptor,
): string | undefined {
  const settings = commission.agents?.[descriptor.agent_name];
  if (!settings) return;
  const offered = {
    enabled_tools: (descriptor.tools ?? [])
      .filter((t) => t.mcp_server_id == null)
      .map((t) => t.name),
    enabled_subagents: (descriptor.subagents ?? []).map((s) => s.name),
    enabled_skills: (descriptor.skills ?? []).map((s) => s.name),
    enabled_mcp_servers: (descriptor.mcp_servers ?? []).map((s) => s.id),
  };
  for (const field of Object.keys(offered) as (keyof typeof offered)[]) {
    const unknown = (settings[field] ?? []).filter(
      (name) => !offered[field].includes(name),
    );
    if (unknown.length)
      return `agents.${descriptor.agent_name}.${field} names items the agent doesn't have: ${unknown.join(", ")}`;
  }
}
export function checkSkillNames(
  commission: Commission,
  _descriptor: AgentDescriptor,
): string | undefined {
  for (const skill of commission.skills ?? []) {
    const name = frontmatterValue(skill.files["SKILL.md"], "name");
    if (name !== skill.name)
      return `skill ${repr(skill.name)}: the frontmatter of its SKILL.md ${name === undefined ? "has no name" : `names ${repr(name)}`}`;
  }
}
export function checkAddedItemsClash(
  commission: Commission,
  descriptor: AgentDescriptor,
): string | undefined {
  for (const server of commission.mcp_servers ?? []) {
    if (descriptor.mcp_servers?.some((s) => s.id === server.id))
      return `MCP server ${repr(server.id)} has the same id as one the agent comes with`;
  }
  for (const skill of commission.skills ?? []) {
    if (descriptor.skills?.some((s) => s.name === skill.name))
      return `skill ${repr(skill.name)} has the same name as one the agent comes with`;
  }
}
export const CHECKS = [
  checkAgentEntry,
  checkAgentVersion,
  checkEnabledItems,
  checkSkillNames,
  checkAddedItemsClash,
] as const;
export function checkCommission(
  commission: Commission,
  descriptor: AgentDescriptor,
): string | undefined {
  for (const check of CHECKS) {
    const message = check(commission, descriptor);
    if (message) return message;
  }
}

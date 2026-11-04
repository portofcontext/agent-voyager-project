import type { Commission } from "../commission.js";
import type { AgentDescriptor, Skill } from "../descriptor.js";
import type { AgentStarted } from "../trajectory.js";
import { parseDefinition } from "../validation.js";
import { frontmatterValue } from "./skill_md.js";

export interface TurnedOff {
  tools: string[];
  subagents: string[];
  skills: string[];
  mcp_servers: string[];
}
export interface RunPlan {
  started: AgentStarted;
  turned_off: TurnedOff;
}

export function planRun(
  commission: Commission,
  descriptor: AgentDescriptor,
): RunPlan {
  const settings = commission.agents?.[descriptor.agent_name] ?? {};
  const allowed = (enabled: string[] | null | undefined, name: string) =>
    enabled == null || enabled.includes(name);
  const toolOn = (tool: NonNullable<AgentDescriptor["tools"]>[number]) =>
    tool.mcp_server_id == null
      ? allowed(settings.enabled_tools, tool.name)
      : allowed(settings.enabled_mcp_servers, tool.mcp_server_id);
  const tools = (descriptor.tools ?? []).filter(toolOn);
  const servers = [
    ...(descriptor.mcp_servers ?? []).filter((s) =>
      allowed(settings.enabled_mcp_servers, s.id),
    ),
    ...(commission.mcp_servers ?? []).map((s) => ({
      id: s.id,
      name: s.name,
      description: s.description,
    })),
  ];
  const skills: Skill[] = [
    ...(descriptor.skills ?? []).filter((s) =>
      allowed(settings.enabled_skills, s.name),
    ),
    ...(commission.skills ?? []).map((s) => ({
      name: s.name,
      description: frontmatterValue(s.files["SKILL.md"], "description") || "",
    })),
  ];
  const subagents = (descriptor.subagents ?? []).filter((s) =>
    allowed(settings.enabled_subagents, s.name),
  );
  const { credential: _credential, ...model } = commission.model;
  return {
    started: parseDefinition("AgentStarted", {
      prompt: commission.prompt,
      system_prompt: commission.system_prompt ?? descriptor.system_prompt,
      model,
      tools: tools.length ? tools : undefined,
      mcp_servers: servers.length ? servers : undefined,
      skills: skills.length ? skills : undefined,
      subagents: subagents.length ? subagents : undefined,
    }),
    turned_off: {
      tools: (descriptor.tools ?? [])
        .filter((t) => !toolOn(t))
        .map((t) => t.name),
      subagents: (descriptor.subagents ?? [])
        .filter((s) => !allowed(settings.enabled_subagents, s.name))
        .map((s) => s.name),
      skills: (descriptor.skills ?? [])
        .filter((s) => !allowed(settings.enabled_skills, s.name))
        .map((s) => s.name),
      mcp_servers: (descriptor.mcp_servers ?? [])
        .filter((s) => !allowed(settings.enabled_mcp_servers, s.id))
        .map((s) => s.id),
    },
  };
}

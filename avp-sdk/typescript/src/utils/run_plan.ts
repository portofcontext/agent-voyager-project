import type { Commission } from "../commission.js";
import type { AgentDescriptor, Skill, Tool } from "../descriptor.js";
import { toolDefinitions, type Agent } from "../trajectory.js";
import { frontmatterValue } from "./skill_md.js";

export interface TurnedOff {
  tools: string[];
  subagents: string[];
  skills: string[];
  mcp_servers: string[];
}
export class RunPlan {
  constructor(
    public prompt: string,
    public system_prompt: string | null | undefined,
    public agent: Agent,
    public turned_off: TurnedOff,
  ) {}
  connected(
    tools: Tool[],
    status: Record<
      string,
      "connected" | "failed" | "needs-auth" | "disabled"
    > = {},
  ): Agent {
    const agent = structuredClone(this.agent),
      extra = agent.extra?.avp;
    if (!extra) throw new Error("the plan's agent has no extra.avp");
    const [definitions, details] = toolDefinitions(tools);
    const allTools = { ...extra.tools, ...details };
    if (Object.keys(allTools).length) extra.tools = allTools;
    if (extra.mcp_servers?.length)
      extra.mcp_servers = extra.mcp_servers.map((s) => ({
        ...s,
        status: status[s.id] ?? "connected",
      }));
    const allDefinitions = [...(agent.tool_definitions ?? []), ...definitions];
    if (allDefinitions.length) agent.tool_definitions = allDefinitions;
    return agent;
  }
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
  const [definitions, details] = toolDefinitions(tools);
  const agent: Agent = {
    name: descriptor.agent_name,
    version: descriptor.agent_version,
    model_name: commission.model.id,
    ...(definitions.length ? { tool_definitions: definitions } : {}),
    extra: {
      avp: {
        model: {
          provider: commission.model.provider,
          ...(commission.model.base_url == null
            ? {}
            : { base_url: commission.model.base_url }),
        },
        ...(Object.keys(details).length ? { tools: details } : {}),
        ...(servers.length ? { mcp_servers: servers } : {}),
        ...(skills.length ? { skills } : {}),
        ...(subagents.length ? { subagents } : {}),
      },
    },
  };
  return new RunPlan(
    commission.prompt,
    commission.system_prompt ?? descriptor.system_prompt ?? null,
    agent,
    {
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
  );
}

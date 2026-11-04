/** Built-in catalogs come from the pinned native server. */
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type {
  OpencodeClient,
  Agent,
  ToolListItem,
} from "@opencode-ai/sdk/v2/client";
import {
  parseDescriptor,
  type AgentDescriptor,
  type Subagent,
  type Tool,
} from "@agent-voyager-project/sdk/descriptor";
import { BASE, BUNDLED, HIDDEN, NAME, permitted } from "./commission.js";
import { Server, data } from "./server.js";
export const VERSION: string = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
).version;
export function tool(item: ToolListItem): Tool {
  return {
    name: item.id,
    description: item.description,
    inputSchema: {
      ...(item.parameters as Record<string, unknown>),
      type: "object",
    },
  };
}
export async function catalog(
  client: OpencodeClient,
  provider: string,
  model: string,
): Promise<Tool[]> {
  return (await data(client.tool.list({ provider, model })))
    .filter((item) => !HIDDEN.has(item.id))
    .map(tool);
}
export async function nativeSkills(client: OpencodeClient) {
  return data(client.app.skills());
}
export function children(
  agents: Agent[],
  tools: Tool[],
  skills: NonNullable<AgentDescriptor["skills"]>,
  parentTools: Record<string, boolean> = {},
): Subagent[] {
  return agents
    .filter(
      (agent) => agent.native && agent.mode === "subagent" && !agent.hidden,
    )
    .map((agent) => ({
      name: agent.name,
      description: agent.description,
      tools: tools.filter((item) =>
        permitted(
          [
            ...agent.permission,
            ...Object.entries(parentTools)
              .filter(([, enabled]) => !enabled)
              .map(([permission]) => ({
                permission,
                pattern: "*",
                action: "deny" as const,
              })),
            ...(agent.permission.some((rule) => rule.permission === "task")
              ? []
              : [
                  { permission: "task", pattern: "*", action: "deny" as const },
                ]),
            ...(agent.permission.some((rule) => rule.permission === "todowrite")
              ? []
              : [
                  {
                    permission: "todowrite",
                    pattern: "*",
                    action: "deny" as const,
                  },
                ]),
          ],
          item.name,
        ),
      ),
      skills: skills.filter((skill) =>
        permitted(agent.permission, "skill", skill.name),
      ),
    }));
}
let cached: Promise<AgentDescriptor> | undefined;
export function describe(): Promise<AgentDescriptor> {
  return (cached ??= (async () => {
    const scratch = mkdtempSync(join(tmpdir(), "avp-opencode-describe-"));
    let server: Server | undefined;
    try {
      server = await Server.start({ cwd: scratch, scratch, config: BASE });
      const client = server.client;
      const lists = await Promise.all([
        catalog(client, "anthropic", "claude-sonnet-4-5"),
        catalog(client, "openai", "gpt-5"),
      ]);
      const ids = await data(client.tool.ids());
      const tools = ids.flatMap((id) => {
        const found = lists.flat().find((item) => item.name === id);
        return found ? [found] : [];
      });
      const skills = (await nativeSkills(client))
        .filter((item) => item.location === "<built-in>")
        .map(({ name, description }) => ({
          name,
          description: description ?? "",
        }));
      const providers = await data(client.provider.list());
      return parseDescriptor({
        avp_version: "0.1",
        agent_name: NAME,
        agent_version: VERSION,
        supported_models: providers.all
          .filter((p) =>
            Object.values(p.models).some((m) => BUNDLED.has(m.api.npm)),
          )
          .map((p) => ({ provider: p.id, id: "*" })),
        tools,
        skills,
        subagents: children(await data(client.app.agents()), tools, skills),
      });
    } finally {
      await server?.close();
      rmSync(scratch, { recursive: true, force: true });
    }
  })());
}

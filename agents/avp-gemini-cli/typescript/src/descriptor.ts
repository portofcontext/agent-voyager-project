/** Describe the native default catalog without connecting to a model. */
import { mkdtempSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as core from "@google/gemini-cli-core";
import { CompleteTaskTool } from "@google/gemini-cli-core/dist/src/tools/complete-task.js";
import {
  parseDescriptor,
  type AgentDescriptor,
  type Tool,
  type Subagent,
} from "@agent-voyager-project/sdk/descriptor";
import { NAME } from "./commission.js";
import { configure, isolated } from "./native.js";
export const VERSION: string = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
).version;
export const CATALOG_MODEL = "gemini-2.5-flash";
const plain = (value: unknown): Record<string, unknown> =>
  JSON.parse(JSON.stringify(value ?? {}));
function declaration(
  d: ReturnType<core.ToolRegistry["getFunctionDeclarations"]>[number],
  server?: string,
): Tool {
  return {
    name: d.name!,
    description: d.description,
    inputSchema: {
      ...plain(d.parametersJsonSchema ?? d.parameters),
      type: "object",
    },
    ...(server ? { mcp_server_id: server } : {}),
  };
}
export function tools(config: core.Config, model: string): Tool[] {
  const registry = config.getToolRegistry();
  return registry.getFunctionDeclarations(model).map((d) => {
    const tool = registry.getTool(d.name!);
    return declaration(
      d,
      tool instanceof core.DiscoveredMCPTool ? tool.serverName : undefined,
    );
  });
}
export function skills(config: core.Config) {
  return config
    .getSkillManager()
    .getSkills()
    .map((s) => ({ name: s.name, description: s.description }));
}
export function subagents(config: core.Config, model: string): Subagent[] {
  const registry = config.getToolRegistry();
  return config
    .getAgentRegistry()
    .getAllDefinitions()
    .map((agent) => {
      if (agent.kind !== "local")
        throw new Error(`unexpected remote agent: ${agent.name}`);
      const byName = new Map(
        tools(config, agent.modelConfig.model ?? model).map((tool) => [
          tool.name,
          tool,
        ]),
      );
      const own = (
        agent.toolConfig?.tools ?? registry.getAllToolNames()
      ).flatMap((ref) => {
        if (typeof ref === "string") {
          const native = registry.getTool(ref);
          return native?.kind !== core.Kind.Agent &&
            ref !== "update_topic" &&
            byName.has(ref)
            ? [byName.get(ref)!]
            : [];
        }
        return [declaration("schema" in ref ? ref.schema : ref)];
      });
      own.push(
        declaration(
          new CompleteTaskTool(
            config.getMessageBus(),
            agent.outputConfig,
            agent.processOutput,
          ).schema,
        ),
      );
      const servers = [
        ...new Set(
          own.flatMap((t) => (t.mcp_server_id ? [t.mcp_server_id] : [])),
        ),
      ];
      return {
        name: agent.name,
        description: agent.description,
        tools: own,
        skills: own.some((tool) => tool.name === "activate_skill")
          ? skills(config)
          : [],
        ...(servers.length
          ? { mcp_servers: servers.map((id) => ({ id })) }
          : {}),
      };
    });
}
let cached: Promise<AgentDescriptor> | undefined;
export function describe(): Promise<AgentDescriptor> {
  return (cached ??= (async () => {
    const root = mkdtempSync(join(tmpdir(), "avp-gemini-describe-"));
    const cwd = join(root, "workspace");
    mkdirSync(cwd);
    try {
      return await isolated(join(root, "home"), async () => {
        const config = await configure(
          join(root, "home"),
          cwd,
          "describe",
          CATALOG_MODEL,
        );
        try {
          return parseDescriptor({
            avp_version: "0.1",
            agent_name: NAME,
            agent_version: VERSION,
            supported_models: [{ provider: "google", id: "*" }],
            tools: tools(config, CATALOG_MODEL),
            skills: skills(config),
            subagents: subagents(config, CATALOG_MODEL),
          });
        } finally {
          await config.dispose();
        }
      });
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  })());
}

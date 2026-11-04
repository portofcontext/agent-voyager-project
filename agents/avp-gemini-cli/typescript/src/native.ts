/** Configure the native headless runtime; it owns all execution and discovery. */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import * as core from "@google/gemini-cli-core";
import type { Commission } from "@agent-voyager-project/sdk/commission";
import type { RunPlan } from "@agent-voyager-project/sdk/utils/run_plan";
import { environment, writeSkills } from "./commission.js";

/** Gemini's process-wide environment/console hooks make runs sequential per process. */
export async function isolated<T>(
  home: string,
  fn: () => Promise<T>,
  systemPrompt?: string | null,
): Promise<T> {
  const vars = ["GEMINI_CLI_HOME", "GEMINI_SYSTEM_MD"] as const;
  const previous = vars.map((key) => process.env[key]);
  const consoleMethods = {
    log: console.log,
    info: console.info,
    debug: console.debug,
  };
  process.env.GEMINI_CLI_HOME = home;
  delete process.env.GEMINI_SYSTEM_MD;
  if (systemPrompt != null) {
    mkdirSync(home, { recursive: true });
    const path = join(home, "system.md");
    writeFileSync(path, systemPrompt);
    process.env.GEMINI_SYSTEM_MD = path;
  }
  console.log = console.info = console.error;
  console.debug = () => {};
  try {
    return await fn();
  } finally {
    Object.assign(console, consoleMethods);
    vars.forEach((key, i) => {
      if (previous[i] === undefined) delete process.env[key];
      else process.env[key] = previous[i];
    });
  }
}

export async function configure(
  home: string,
  cwd: string,
  sessionId: string,
  model: string,
  commission?: Commission,
  plan?: RunPlan,
): Promise<core.Config> {
  if (commission) writeSkills(commission, join(home, ".gemini", "skills"));
  const exclude = ["ask_user", ...(plan?.turned_off.tools ?? [])];
  const mcpServers = Object.fromEntries(
    (commission?.mcp_servers ?? []).map((server) => {
      if (server.type === "stdio")
        return [
          server.id,
          new core.MCPServerConfig(
            server.command[0],
            server.command.slice(1),
            Object.fromEntries(
              Object.entries(server.env ?? {}).map(([key, value]) => [
                key,
                typeof value === "string" ? value : environment(value),
              ]),
            ),
          ),
        ];
      return [
        server.id,
        new core.MCPServerConfig(
          undefined,
          undefined,
          undefined,
          undefined,
          undefined,
          server.url,
          Object.fromEntries(
            Object.entries(server.headers ?? {})
              .filter(
                ([, value]) => typeof value === "string" || !("proxy" in value),
              )
              .map(([key, value]) => [
                key,
                typeof value === "string"
                  ? value
                  : environment(value as { env: string }),
              ]),
          ),
        ),
      ];
    }),
  );
  const policyEngineConfig = await core.createPolicyEngineConfig(
    { tools: { exclude }, mcpServers },
    core.ApprovalMode.YOLO,
    undefined,
    false,
  );
  const config = new core.Config({
    sessionId,
    targetDir: cwd,
    cwd,
    model,
    debugMode: false,
    approvalMode: core.ApprovalMode.YOLO,
    policyEngineConfig,
    interactive: false,
    trustedFolder: true,
    usageStatisticsEnabled: false,
    fileFiltering: { enableFileWatcher: false },
    telemetry: { enabled: false },
    excludeTools: exclude,
    mcpServers,
    extensionLoader: new core.SimpleExtensionLoader([]),
    enableHooks: false,
    agents: {
      overrides: Object.fromEntries(
        (plan?.turned_off.subagents ?? []).map((name) => [
          name,
          { enabled: false },
        ]),
      ),
    },
    disabledSkills: plan?.turned_off.skills ?? [],
    disableLoopDetection: true,
    skipNextSpeakerCheck: true,
    disableLLMCorrection: true,
    disableModelRouterForAuth: [core.AuthType.USE_GEMINI],
    dynamicModelConfiguration: false,
    autoDistillation: false,
    experimentalAutoMemory: false,
    compressionThreshold: 1,
    modelConfigServiceConfig: {
      modelIdResolutions: { [model]: { default: model } },
    },
  });
  // Core has no switch for project agent/skill discovery. Redirect only those
  // storage paths; tool execution still uses the launcher's working directory.
  config.storage.getProjectAgentsDir = () => join(home, "project-agents");
  config.storage.getProjectSkillsDir = () => join(home, "project-skills");
  config.storage.getProjectAgentSkillsDir = () =>
    join(home, "project-agent-skills");
  try {
    await config.initialize();
    return config;
  } catch (error) {
    await config.dispose();
    throw error;
  }
}

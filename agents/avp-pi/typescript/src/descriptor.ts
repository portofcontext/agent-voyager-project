/** The native product's default tools and bundled providers, without discovery. */
import { readFileSync } from "node:fs";
import {
  InMemoryCredentialStore,
  InMemoryModelsStore,
} from "@earendil-works/pi-ai";
import {
  createCodingTools,
  ModelRuntime,
} from "@earendil-works/pi-coding-agent";
import {
  parseDescriptor,
  type AgentDescriptor,
} from "@agent-voyager-project/sdk/descriptor";
import { AGENT_NAME } from "./commission.js";

export const VERSION: string = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
).version;

export function runtime(): Promise<ModelRuntime> {
  return ModelRuntime.create({
    credentials: new InMemoryCredentialStore(),
    modelsStore: new InMemoryModelsStore(),
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
}

let cached: Promise<AgentDescriptor> | undefined;
export function describe(): Promise<AgentDescriptor> {
  return (cached ??= (async () => {
    const models = await runtime();
    return parseDescriptor({
      avp_version: "0.1",
      agent_name: AGENT_NAME,
      agent_version: VERSION,
      supported_models: [
        ...new Set(models.getModels().map((m) => m.provider)),
      ].map((provider) => ({ provider, id: "*" })),
      tools: createCodingTools(process.cwd()).map((tool) => ({
        name: tool.name,
        description: tool.description,
        inputSchema: JSON.parse(JSON.stringify(tool.parameters)),
      })),
    });
  })());
}

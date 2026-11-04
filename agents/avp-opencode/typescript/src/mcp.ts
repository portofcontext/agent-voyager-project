/** The native API omits MCP schemas; discover them separately and fail visibly. */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type {
  Commission,
  EnvSecret,
} from "@agent-voyager-project/sdk/commission";
import type { Tool } from "@agent-voyager-project/sdk/descriptor";
import { envSecret } from "./commission.js";
export class McpFailure extends Error {}
export async function discover(
  commission: Commission,
  env: NodeJS.ProcessEnv,
  taken: Set<string>,
): Promise<Tool[]> {
  const tools: Tool[] = [];
  for (const server of commission.mcp_servers ?? []) {
    const client = new Client({
      name: "avp-opencode-discovery",
      version: "0.1",
    });
    try {
      const transport =
        server.type === "stdio"
          ? new StdioClientTransport({
              command: server.command[0]!,
              args: server.command.slice(1),
              env: Object.fromEntries(
                Object.entries({
                  ...env,
                  ...Object.fromEntries(
                    Object.entries(server.env ?? {}).map(([key, value]) => [
                      key,
                      typeof value === "string" ? value : envSecret(value, env),
                    ]),
                  ),
                }).filter(
                  (entry): entry is [string, string] => entry[1] !== undefined,
                ),
              ),
              stderr: "pipe",
            })
          : new StreamableHTTPClientTransport(new URL(server.url), {
              requestInit: {
                headers: Object.fromEntries(
                  Object.entries(server.headers ?? {})
                    .filter(([, v]) => typeof v === "string" || !("proxy" in v))
                    .map(([key, value]) => [
                      key,
                      typeof value === "string"
                        ? value
                        : envSecret(value as EnvSecret, env),
                    ]),
                ),
              },
            });
      await client.connect(transport, { timeout: 30_000 });
      const listed = await client.listTools(undefined, { timeout: 30_000 });
      for (const item of listed.tools) {
        const name = `${server.id.replace(/[^a-zA-Z0-9_-]/g, "_")}_${item.name.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
        if (taken.has(name))
          throw new Error(
            `MCP tool name collides after native sanitization: ${name}`,
          );
        taken.add(name);
        tools.push({
          name,
          description: item.description,
          inputSchema: item.inputSchema,
          outputSchema: item.outputSchema,
          mcp_server_id: server.id,
        });
      }
    } catch (error) {
      throw new McpFailure(
        `${server.id}: ${error instanceof Error ? error.message : String(error)}`,
        { cause: error },
      );
    } finally {
      await client.close();
    }
  }
  return tools;
}

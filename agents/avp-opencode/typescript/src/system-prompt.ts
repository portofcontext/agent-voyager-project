/** A private bridge from OpenCode's assembled-prompt hook to the Recorder. */
import { randomBytes } from "node:crypto";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

export class SystemPrompt {
  sessionID?: string;
  ready = false;
  failure?: unknown;
  private constructor(
    private server: Server,
    readonly pluginOptions: { url: string; token: string },
  ) {}

  static async open(
    override: string | null | undefined,
    started: (prompt: string) => Promise<void>,
  ): Promise<SystemPrompt> {
    const token = randomBytes(24).toString("base64url");
    const server = createServer((req, res) => {
      if (
        req.method !== "POST" ||
        req.headers.authorization !== `Bearer ${token}`
      ) {
        res.writeHead(403).end();
        return;
      }
      void (async () => {
        let size = 0;
        const chunks: Buffer[] = [];
        for await (const chunk of req) {
          size += chunk.length;
          if (size > 4 * 1024 * 1024)
            throw new Error("system prompt exceeds bridge limit");
          chunks.push(Buffer.from(chunk));
        }
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        if (req.url === "/ready") {
          bridge.ready = true;
          res.writeHead(204).end();
          return;
        }
        if (
          req.url !== "/system" ||
          !Array.isArray(body.system) ||
          !body.system.every((part: unknown) => typeof part === "string")
        )
          throw new Error("invalid native system-prompt report");
        let system: string[] = body.system;
        if (bridge.sessionID && body.sessionID === bridge.sessionID) {
          if (override != null) system = override === "" ? [] : [override];
          // The native hook awaits this write before sending the model request.
          // Child sessions retain their own native prompts.
          await started(system.join("\n"));
        }
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify({ system }));
      })().catch((error: unknown) => {
        bridge.failure = error;
        res.writeHead(500).end("AVP system-prompt hook failed");
      });
    });
    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", resolve);
    });
    const { port } = server.address() as AddressInfo;
    const bridge = new SystemPrompt(server, {
      url: `http://127.0.0.1:${port}`,
      token,
    });
    return bridge;
  }

  async close(): Promise<void> {
    this.server.closeAllConnections();
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }
}

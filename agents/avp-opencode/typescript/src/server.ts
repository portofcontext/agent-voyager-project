/** One pinned native server per run, with private state and no startup downloads. */
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { copyFileSync, mkdirSync, symlinkSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Agent, fetch as pooledFetch } from "undici";
import {
  createOpencodeClient,
  type OpencodeClient,
} from "@opencode-ai/sdk/v2/client";

export function binary(): string {
  // The package's build-time installer chooses and copies its pinned platform binary.
  return join(
    dirname(fileURLToPath(import.meta.resolve("opencode-ai/package.json"))),
    "bin",
    "opencode.exe",
  );
}
export async function data<T>(
  request: Promise<{ data?: T; error?: unknown; response?: Response }>,
): Promise<T> {
  const result = await request;
  if (result.error !== undefined || result.data === undefined)
    throw new Error(
      `OpenCode request failed (${result.response?.status}): ${JSON.stringify(result.error)}`,
    );
  return result.data;
}
export interface ServerOptions {
  cwd: string;
  scratch: string;
  config: Record<string, unknown>;
  env?: Record<string, string | undefined>;
  prompt?: { url: string; token: string };
}
export class Server {
  private constructor(
    readonly client: OpencodeClient,
    readonly exited: Promise<string>,
    private proc: ChildProcess,
    private pool: Agent,
    private onExit: () => void,
  ) {}
  static async start(options: ServerOptions): Promise<Server> {
    const password = randomBytes(24).toString("base64url");
    const home = join(options.scratch, "home");
    mkdirSync(home, { recursive: true });
    // Native plugin initialization checks this directory's npm dependencies.
    // Reuse the locked build-time installation, with private configuration and
    // metadata, so that it never tries to fetch @opencode-ai/plugin at startup.
    const config = join(options.scratch, "config", "opencode");
    const project = fileURLToPath(new URL("../../", import.meta.url));
    mkdirSync(config, { recursive: true });
    for (const file of ["package.json", "package-lock.json"])
      copyFileSync(join(project, file), join(config, file));
    symlinkSync(
      join(project, "node_modules"),
      join(config, "node_modules"),
      "junction",
    );
    const inherited = Object.fromEntries(
      Object.entries({ ...process.env, ...options.env }).filter(
        ([key, value]) => value !== undefined && !key.startsWith("OPENCODE_"),
      ),
    );
    const proc = spawn(
      binary(),
      ["serve", "--hostname=127.0.0.1", "--port=0"],
      {
        cwd: options.cwd,
        detached: true,
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...inherited,
          XDG_CONFIG_HOME: join(options.scratch, "config"),
          XDG_DATA_HOME: join(options.scratch, "data"),
          XDG_STATE_HOME: join(options.scratch, "state"),
          XDG_CACHE_HOME: join(options.scratch, "cache"),
          OPENCODE_TEST_HOME: home,
          OPENCODE_CONFIG_CONTENT: JSON.stringify({
            ...options.config,
            plugin: options.prompt
              ? [
                  [
                    new URL("./prompt-plugin.js", import.meta.url).href,
                    options.prompt,
                  ],
                ]
              : [],
          }),
          OPENCODE_SERVER_PASSWORD: password,
          OPENCODE_CLIENT: "avp",
          // Pure mode suppresses even explicitly configured plugins. Runs load
          // only our bundled hook; the Descriptor needs no plugins.
          OPENCODE_PURE: options.prompt ? "0" : "1",
          OPENCODE_DISABLE_PROJECT_CONFIG: "1",
          OPENCODE_DISABLE_AUTOUPDATE: "1",
          OPENCODE_DISABLE_MODELS_FETCH: "1",
          OPENCODE_DISABLE_DEFAULT_PLUGINS: "1",
          OPENCODE_DISABLE_CLAUDE_CODE: "1",
          OPENCODE_DISABLE_EXTERNAL_SKILLS: "1",
          OPENCODE_DISABLE_LSP_DOWNLOAD: "1",
          OPENCODE_DISABLE_EMBEDDED_WEB_UI: "1",
        },
      },
    );
    const kill = (signal: NodeJS.Signals) => {
      if (proc.pid)
        try {
          process.kill(-proc.pid, signal);
        } catch {}
    };
    const onExit = () => kill("SIGKILL");
    process.on("exit", onExit);
    let logs = "";
    proc.stderr!.on("data", (chunk: Buffer) => {
      logs = (logs + chunk).slice(-2000);
    });
    const exited = new Promise<string>((resolve) => {
      proc.once("error", (error) =>
        resolve(`OpenCode failed to start: ${error.message}`),
      );
      proc.once("exit", (code, signal) =>
        resolve(`OpenCode exited (${signal ?? code}): ${logs}`),
      );
    });
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const url = await Promise.race([
        new Promise<string>((resolve) => {
          let buffer = "";
          proc.stdout!.on("data", (chunk: Buffer) => {
            buffer += chunk;
            const match = buffer.match(
              /opencode server listening on (https?:\/\/\S+)/,
            );
            if (match) resolve(match[1]!);
          });
        }),
        exited.then((why) => {
          throw new Error(why);
        }),
        new Promise<never>((_, reject) => {
          timer = setTimeout(
            () => reject(new Error("OpenCode startup timed out")),
            30_000,
          );
        }),
      ]);
      const pool = new Agent();
      const client = createOpencodeClient({
        baseUrl: url,
        directory: options.cwd,
        headers: {
          Authorization: `Basic ${Buffer.from(`opencode:${password}`).toString("base64")}`,
        },
        fetch: ((input: Request) =>
          pooledFetch(input.url, {
            method: input.method,
            headers: [...input.headers],
            body: input.body,
            signal: input.signal,
            duplex: "half",
            dispatcher: pool,
          })) as unknown as typeof fetch,
      });
      return new Server(client, exited, proc, pool, onExit);
    } catch (error) {
      kill("SIGKILL");
      process.off("exit", onExit);
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  async close(): Promise<void> {
    const timeout = (ms: number) =>
      new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, ms);
        timer.unref();
      });
    if (this.proc.exitCode === null && this.proc.signalCode === null) {
      await Promise.race([
        this.client.global.dispose().catch(() => {}),
        timeout(1000),
      ]);
      try {
        process.kill(-this.proc.pid!, "SIGTERM");
      } catch {}
      await Promise.race([this.exited, timeout(2000)]);
      if (this.proc.exitCode === null && this.proc.signalCode === null)
        try {
          process.kill(-this.proc.pid!, "SIGKILL");
        } catch {}
    }
    await this.pool.destroy().catch(() => {});
    process.off("exit", this.onExit);
  }
}

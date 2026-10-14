/**
 * One hermetic `opencode serve` per run.
 *
 * The server is the pinned native binary from the platform package
 * (`opencode-<os>-<arch>`), started in its own process group on
 * `127.0.0.1` with an ephemeral port and a random password. OpenCode's
 * config, data, and state directories point into a scratch directory, so no
 * user config, auth file, session database, or plugin is read, and the
 * Commission's config arrives inline (`OPENCODE_CONFIG_CONTENT`). External
 * plugins, sharing, autoupdate, model-catalog fetches, Claude Code prompt and
 * skill discovery, and LSP downloads are off; the catalog is the one the
 * binary bundles. The cache directory is the adapter's own
 * (`$XDG_CACHE_HOME/avp-opencode`) so OpenCode's ripgrep download, when `rg`
 * is not on PATH, happens once. Child processes (tools, stdio MCP servers)
 * inherit these XDG directories.
 *
 * `close` disposes the server (closing MCP connections), then kills the
 * process group; an exit hook kills it if Node exits first.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

import { createOpencodeClient, type OpencodeClient } from "@opencode-ai/sdk/v2/client";

const START_TIMEOUT_MS = 60_000;
const STOP_GRACE_MS = 3_000;

export interface ServerOptions {
  /** The workspace OpenCode works in. */
  cwd: string;
  /** Scratch directory for OpenCode's config, data, and state; the caller removes it. */
  scratch: string;
  /** Inline OpenCode config. */
  config: Record<string, unknown>;
  /** Extra environment for the server (credentials in tests, say). */
  env?: Record<string, string | undefined>;
  /** The `opencode` executable; defaults to the platform package's. */
  binary?: string;
}

export class OpencodeServer {
  private readonly onExit = () => this.kill("SIGKILL");

  private constructor(
    readonly url: string,
    readonly client: OpencodeClient,
    /** Resolves with a description once the server process is gone. */
    readonly exited: Promise<string>,
    private readonly proc: ChildProcess,
    private readonly output: () => string,
  ) {
    process.on("exit", this.onExit);
  }

  static async start(opts: ServerOptions): Promise<OpencodeServer> {
    const password = randomBytes(18).toString("base64url");
    const proc = spawn(opts.binary ?? opencodeBinary(), ["serve", "--hostname=127.0.0.1", "--port=0"], {
      cwd: opts.cwd,
      env: serverEnv(opts, password),
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
    });
    let output = "";
    const exited = new Promise<string>((resolve) => {
      proc.once("error", (err) => resolve(`could not start opencode: ${err.message}`));
      proc.once("exit", (code, signal) =>
        resolve(`opencode server exited (${signal ?? `code ${code}`})${tail(output) ? `: ${tail(output)}` : ""}`),
      );
    });
    proc.stderr!.on("data", (chunk: Buffer) => (output = (output + chunk.toString()).slice(-4000)));
    const url = await new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`opencode server did not start in ${START_TIMEOUT_MS}ms`)), START_TIMEOUT_MS);
      let buffered = "";
      proc.stdout!.on("data", (chunk: Buffer) => {
        buffered += chunk.toString();
        const match = buffered.match(/opencode server listening on (https?:\/\/\S+)/);
        if (match) {
          clearTimeout(timer);
          resolve(match[1]!);
        }
      });
      void exited.then((why) => {
        clearTimeout(timer);
        reject(new Error(why));
      });
    }).catch((err) => {
      killGroup(proc, "SIGKILL");
      throw err;
    });
    proc.stdout!.resume();
    const auth = `Basic ${Buffer.from(`opencode:${password}`).toString("base64")}`;
    const client = createOpencodeClient({ baseUrl: url, directory: opts.cwd, headers: { Authorization: auth } });
    return new OpencodeServer(url, client, exited, proc, () => output);
  }

  /** The tail of the server's log output, for error messages. */
  get log(): string {
    return tail(this.output());
  }

  /** Dispose OpenCode's instances, then stop the process group. Safe to call twice. */
  async close(): Promise<void> {
    if (this.proc.exitCode === null && this.proc.signalCode === null) {
      await withTimeout(this.client.global.dispose(), STOP_GRACE_MS).catch(() => {});
      this.kill("SIGTERM");
      const stopped = await withTimeout(this.exited, STOP_GRACE_MS).then(
        () => true,
        () => false,
      );
      if (!stopped) this.kill("SIGKILL");
    }
    process.off("exit", this.onExit);
  }

  private kill(signal: NodeJS.Signals): void {
    killGroup(this.proc, signal);
  }
}

function killGroup(proc: ChildProcess, signal: NodeJS.Signals): void {
  if (proc.pid === undefined) return;
  try {
    process.kill(-proc.pid, signal);
  } catch {
    // Already gone.
  }
}

function serverEnv(opts: ServerOptions, password: string): Record<string, string> {
  const env: Record<string, string | undefined> = { ...process.env };
  for (const key of Object.keys(env)) {
    if (key.startsWith("OPENCODE_") || key.startsWith("OTEL_")) delete env[key];
  }
  const cache = join(process.env.XDG_CACHE_HOME || join(homedir(), ".cache"), "avp-opencode");
  const home = join(opts.scratch, "home");
  for (const dir of [cache, home]) mkdirSync(dir, { recursive: true });
  Object.assign(env, {
    XDG_CONFIG_HOME: join(opts.scratch, "config"),
    XDG_DATA_HOME: join(opts.scratch, "data"),
    XDG_STATE_HOME: join(opts.scratch, "state"),
    XDG_CACHE_HOME: cache,
    // OpenCode's own notion of home: `~/.opencode`, `~/.claude`, and
    // `~/.agents` discovery. Tools still see the real home.
    OPENCODE_TEST_HOME: home,
    OPENCODE_CONFIG_CONTENT: JSON.stringify(opts.config),
    OPENCODE_SERVER_PASSWORD: password,
    // A headless client: no `question` tool asking a user who isn't there.
    OPENCODE_CLIENT: "avp",
    OPENCODE_PURE: "1",
    OPENCODE_DISABLE_AUTOUPDATE: "1",
    OPENCODE_DISABLE_MODELS_FETCH: "1",
    OPENCODE_DISABLE_DEFAULT_PLUGINS: "1",
    OPENCODE_DISABLE_CLAUDE_CODE: "1",
    OPENCODE_DISABLE_EXTERNAL_SKILLS: "1",
    OPENCODE_DISABLE_LSP_DOWNLOAD: "1",
    OPENCODE_DISABLE_EMBEDDED_WEB_UI: "1",
    ...opts.env,
  });
  return Object.fromEntries(Object.entries(env).filter((e): e is [string, string] => e[1] !== undefined));
}

/** The platform package's `opencode` executable, as OpenCode's own installer picks it. */
export function opencodeBinary(): string {
  const os = { darwin: "darwin", linux: "linux", win32: "windows" }[process.platform as string] ?? process.platform;
  const base = `opencode-${os}-${process.arch}`;
  const musl = os === "linux" && isMusl();
  const names = musl
    ? [`${base}-musl`, `${base}-baseline-musl`, base, `${base}-baseline`]
    : [base, `${base}-baseline`, `${base}-musl`, `${base}-baseline-musl`];
  const require = createRequire(import.meta.url);
  for (const name of names) {
    try {
      const bin = join(dirname(require.resolve(`${name}/package.json`)), "bin", "opencode");
      if (existsSync(bin)) return bin;
    } catch {
      // Not installed; try the next variant.
    }
  }
  throw new Error(`no OpenCode binary for ${process.platform}-${process.arch} (expected the ${base} package)`);
}

function isMusl(): boolean {
  if (existsSync("/etc/alpine-release")) return true;
  const header = (process.report?.getReport() as { header?: { glibcVersionRuntime?: string } } | undefined)?.header;
  return header !== undefined && !header.glibcVersionRuntime;
}

function tail(text: string): string {
  return text.trim().split("\n").slice(-5).join("\n");
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timed out")), ms);
    promise.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

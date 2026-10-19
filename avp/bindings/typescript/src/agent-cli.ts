/**
 * The stock agent command line.
 *
 * Every AVP agent answers the same three commands, which `avp-conformance`
 * and the `avp` CLI drive:
 *
 * - `ping --out <path>`: write `{"type":"pong"}` and exit, without booting
 *   the agent.
 * - `describe [--out <path>]`: print the agent's descriptor JSON (to `--out`,
 *   or stdout).
 * - `run --commission <json|path> [--built-in <json|path>] --out <path>`: run
 *   the Commission and write the trajectory to `--out` as NDJSON.
 *
 * An adapter supplies two functions and gets the whole contract:
 *
 * ```ts
 * process.exitCode = await main({ describe, run });
 * ```
 *
 * `run` resolves once the trajectory is closed with `agent_stopped`,
 * including runs that end in an expected failure (a fail-fast Commission
 * check, a provider auth or rate-limit error, a refusal); it rejects only for
 * a crash, after recording `error_occurred` and `agent_stopped`. `main` then
 * returns 1 with the error on stderr.
 *
 * `--built-in` is the conformance fixture of the agent's pretend defaults: its
 * `system_prompt` and `prompt` seed the Commission when it leaves them unset
 * (the Commission wins). Matches the Python `avp.agent_cli` and the Rust
 * `avp::agent_cli`.
 */
import { readFileSync, writeFileSync } from "node:fs";

import type { AgentDescriptor, Commission } from "./index.js";
import { FileSink } from "./sink.js";

export interface AgentEntrypoint {
  describe: () => AgentDescriptor | Promise<AgentDescriptor>;
  run: (commission: Commission, sink: FileSink) => Promise<void>;
}

const USAGE = `usage: <agent> ping --out <path>
       <agent> describe [--out <path>]
       <agent> run --commission <json|path> [--built-in <json|path>] --out <path>`;

class UsageError extends Error {}

/** Parse `argv` (default: `process.argv` after the script) and dispatch. Returns the exit code. */
export async function main(agent: AgentEntrypoint, argv = process.argv.slice(2)): Promise<number> {
  try {
    await dispatch(agent, argv);
    return 0;
  } catch (err) {
    if (err instanceof UsageError) {
      process.stderr.write(`error: ${err.message}\n${USAGE}\n`);
      return 2;
    }
    process.stderr.write(`error: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`);
    return 1;
  }
}

/** `main` over explicit arguments (without the program name); throws instead of returning a code. */
export async function dispatch(agent: AgentEntrypoint, argv: string[]): Promise<void> {
  const [cmd, ...rest] = argv;
  if (!cmd) throw new UsageError("missing command");
  const flags = parseFlags(rest);
  const need = (key: string): string => {
    const value = flags.get(key);
    if (value === undefined) throw new UsageError(`${cmd} needs --${key}`);
    return value;
  };
  switch (cmd) {
    case "ping":
      writeFileSync(need("out"), '{"type":"pong"}\n');
      return;
    case "describe": {
      const descriptor = await inWorkspace(agent.describe);
      const text = JSON.stringify(descriptor, null, 2);
      const out = flags.get("out");
      if (out !== undefined) writeFileSync(out, `${text}\n`);
      else process.stdout.write(`${text}\n`);
      return;
    }
    case "run": {
      const commission = readJsonArg(need("commission")) as Commission;
      const builtIn = flags.get("built-in");
      if (builtIn !== undefined) applyBuiltIn(commission, readJsonArg(builtIn) as Record<string, unknown>);
      const sink = new FileSink(need("out"));
      try {
        await inWorkspace(() => agent.run(commission, sink));
      } finally {
        sink.close();
      }
      return;
    }
    default:
      throw new UsageError(`unknown command ${JSON.stringify(cmd)}`);
  }
}

/**
 * Run `fn` inside `AVP_WORKSPACE` when the launcher supplies one. CLI file
 * arguments resolve before entering it; the previous directory is restored
 * even on errors.
 */
async function inWorkspace<T>(fn: () => T | Promise<T>): Promise<T> {
  const workspace = process.env.AVP_WORKSPACE;
  if (!workspace) return await fn();
  const previous = process.cwd();
  process.chdir(workspace);
  try {
    return await fn();
  } finally {
    process.chdir(previous);
  }
}

function parseFlags(rest: string[]): Map<string, string> {
  const flags = new Map<string, string>();
  for (let i = 0; i < rest.length; i++) {
    const arg = rest[i]!;
    if (!arg.startsWith("--")) throw new UsageError(`unexpected argument ${JSON.stringify(arg)}`);
    const name = arg.slice(2);
    const eq = name.indexOf("=");
    if (eq >= 0) {
      flags.set(name.slice(0, eq), name.slice(eq + 1));
    } else {
      const value = rest[++i];
      if (value === undefined) throw new UsageError(`--${name} needs a value`);
      flags.set(name, value);
    }
  }
  return flags;
}

/** Inline JSON (a leading `{` / `[`) or a path to a JSON file. */
export function readJsonArg(value: string): unknown {
  const trimmed = value.trimStart();
  return JSON.parse(trimmed.startsWith("{") || trimmed.startsWith("[") ? value : readFileSync(value, "utf8"));
}

/** Seed `system_prompt` / `prompt` from the fixture where the Commission leaves them unset. */
export function applyBuiltIn(commission: Commission, builtIn: Record<string, unknown>): void {
  if (commission.system_prompt == null && typeof builtIn.system_prompt === "string") {
    commission.system_prompt = builtIn.system_prompt;
  }
  if (commission.prompt == null && typeof builtIn.prompt === "string") {
    commission.prompt = builtIn.prompt;
  }
}

import { dirname, basename } from "node:path";
import { atomicWrite, writeArtifacts } from "./artifacts.js";
import { readFileSync, writeFileSync } from "node:fs";
import { Command, CommanderError } from "commander";
import { parseDescriptor, type AgentDescriptor } from "./descriptor.js";
import { avpMetadata, type TrajectorySink } from "./trajectory.js";
import type { JsonValue } from "./reports.js";
export type { TrajectorySink } from "./trajectory.js";

export type RunFn = (
  received: JsonValue,
  sink: TrajectorySink,
  signal: AbortSignal,
) => Promise<void>;
export type DescribeFn = () => AgentDescriptor | Promise<AgentDescriptor>;

export function readCommission(value: string): JsonValue {
  const text = value.trimStart().startsWith("{")
    ? value
    : readFileSync(value, "utf8");
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
function stdout(text: string): Promise<void> {
  return new Promise((resolve, reject) =>
    process.stdout.write(text, (error) => (error ? reject(error) : resolve())),
  );
}
export function trajectorySink(out?: string): TrajectorySink {
  return async (snapshot) => {
    const text = `${JSON.stringify(snapshot.trajectory, undefined, 2)}\n`;
    if (out === undefined) {
      if (avpMetadata(snapshot.trajectory).complete) {
        if (snapshot.assets.size)
          throw new Error("media requires --out with a file path");
        await stdout(text);
      }
      return;
    }
    const directory = dirname(out);
    const files = new Map(snapshot.artifacts ?? []);
    for (const [name, bytes] of snapshot.assets) {
      const old = files.get(name);
      if (
        old &&
        (old.role !== "output" ||
          !Buffer.from(old.content).equals(Buffer.from(bytes)))
      )
        throw new Error(`conflicting media artifact: ${name}`);
      files.set(name, { content: bytes, role: "output" });
    }
    if (basename(out) === "artifacts.json" || files.has(basename(out)))
      throw new Error("an artifact cannot replace the trajectory");
    writeArtifacts(
      directory,
      snapshot.trajectory.session_id ?? "unknown",
      files,
    );
    atomicWrite(out, Buffer.from(text));
  };
}
async function write(out: string | undefined, text: string): Promise<void> {
  if (out === undefined) await stdout(text);
  else writeFileSync(out, text);
}

export async function main({
  run,
  describe,
  prog = "agent",
  argv = process.argv.slice(2),
}: {
  run: RunFn;
  describe: DescribeFn;
  prog?: string;
  argv?: string[];
}): Promise<number> {
  const app = new Command(prog)
    .description("An AVP agent. Not part of the AVP spec.")
    .addHelpCommand(false)
    .exitOverride();
  let interrupted = false;
  app
    .command("ping")
    .description("Check that the agent runs, without loading it.")
    .option("--out <path>", "Where to write it (default: stdout).")
    .action(async ({ out }: { out?: string }) => {
      await write(out, '{"type": "pong", "avp_version": "0.1"}\n');
    });
  app
    .command("describe")
    .description("Write the agent's Descriptor.")
    .option("--out <path>", "Where to write it (default: stdout).")
    .action(async ({ out }: { out?: string }) => {
      await write(
        out,
        `${JSON.stringify(parseDescriptor(await describe()), undefined, 2)}\n`,
      );
    });
  app
    .command("run")
    .description("Run a Commission and write its Trajectory as ATIF JSON.")
    .requiredOption("--commission <path-or-json>", "A path, or inline JSON.")
    .requiredOption("--out <path>", "Where to write the ATIF document, or -.")
    .action(
      async ({ commission, out }: { commission: string; out: string }) => {
        const sink = trajectorySink(out === "-" ? undefined : out);
        const received = readCommission(commission);
        const controller = new AbortController();
        const interrupt = () => {
          interrupted = true;
          controller.abort();
        };
        process.on("SIGINT", interrupt);
        process.on("SIGTERM", interrupt);
        try {
          await run(received, sink, controller.signal);
        } catch (error) {
          if (!controller.signal.aborted) throw error;
        } finally {
          process.off("SIGINT", interrupt);
          process.off("SIGTERM", interrupt);
        }
      },
    );
  try {
    await app.parseAsync(argv, { from: "user" });
  } catch (error) {
    if (error instanceof CommanderError) return error.exitCode === 0 ? 0 : 2;
    process.stderr.write(`${(error as Error).message}\n`);
    return 1;
  }
  return interrupted ? 130 : 0;
}

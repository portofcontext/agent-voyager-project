import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { setTimeout } from "node:timers/promises";
import { main, ndjsonSink } from "../src/agent_cli.js";
import { Recorder } from "../src/recorder.js";
import { parseTrajectoryEvent } from "../src/trajectory.js";

const fixture = new URL("./fixtures/agent.js", import.meta.url);
const commission = (prompt: string) =>
  JSON.stringify({
    avp_version: "0.1",
    run_id: "r",
    prompt,
    model: { provider: "p", id: "m" },
  });
const events = (text: string) =>
  text
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
const cli = (...argv: string[]) =>
  spawnSync(process.execPath, [fixture.pathname, ...argv], {
    encoding: "utf8",
  });

test("CLI writes complete and refused trajectories, with paths or inline JSON", async () => {
  const dir = await mkdtemp(join(tmpdir(), "avp-cli-"));
  try {
    const c = join(dir, "commission.json");
    const out = join(dir, "events.ndjson");
    await writeFile(c, commission("Hi"));
    await writeFile(out, "old contents");
    const result = cli("run", "--commission", c, "--out", out);
    assert.equal(result.status, 0, result.stderr);
    const written = events(await readFile(out, "utf8"));
    assert.deepEqual(
      written.map((event) => event.type),
      [
        "run_requested",
        "agent_described",
        "agent_started",
        "assistant_message",
        "agent_stopped",
      ],
    );
    written.forEach((event) => assert.ok(parseTrajectoryEvent(event)));
    assert.equal(
      cli("run", "--commission", commission("Hi"), "--out", "-").status,
      0,
    );
    await writeFile(c, "not JSON");
    const refusal = cli("run", "--commission", c, "--out", "-");
    assert.equal(refusal.status, 0, refusal.stderr);
    assert.equal(events(refusal.stdout)[0].data.commission, "not JSON");
    assert.equal(events(refusal.stdout).at(-1).type, "error_occurred");
    assert.equal(JSON.parse(cli("describe").stdout).agent_name, "example");
    assert.equal(JSON.parse(cli("ping").stdout).type, "pong");
  } finally {
    await rm(dir, { recursive: true });
  }
});

test("ping does not load the agent, and the file sink reopens for each event", async () => {
  const dir = await mkdtemp(join(tmpdir(), "avp-cli-"));
  try {
    assert.equal(
      await main({
        argv: ["ping", "--out", join(dir, "pong.json")],
        run: async () => {
          throw new Error("ping called run");
        },
        describe: () => {
          throw new Error("ping called describe");
        },
      }),
      0,
    );
    const path = join(dir, "events.ndjson");
    const archive = join(dir, "archived.ndjson");
    const rec = new Recorder(ndjsonSink(path));
    await rec.start({ prompt: "Hi", model: { provider: "p", id: "m" } });
    await rename(path, archive);
    await rec.stop("converged");
    assert.equal(
      events(await readFile(archive, "utf8"))[0].type,
      "agent_started",
    );
    assert.equal(events(await readFile(path, "utf8"))[0].type, "agent_stopped");
  } finally {
    await rm(dir, { recursive: true });
  }
});

test("crashes and argument errors exit nonzero", () => {
  const crash = cli("run", "--commission", commission("crash"), "--out", "-");
  assert.equal(crash.status, 1);
  assert.match(crash.stderr, /fixture crash/);
  assert.equal(cli("run", "--out", "-").status, 2);
  assert.equal(cli("run", "--help").status, 0);
});

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  test(
    `${signal} ends the trajectory and exits 130`,
    { skip: process.platform === "win32", timeout: 15_000 },
    async () => {
      const child = spawn(
        process.execPath,
        [
          fixture.pathname,
          "run",
          "--commission",
          commission("wait"),
          "--out",
          "-",
        ],
        { stdio: ["ignore", "pipe", "pipe"] },
      );
      let output = "";
      let errors = "";
      child.stdout.on("data", (chunk) => {
        output += chunk;
      });
      child.stderr.on("data", (chunk) => {
        errors += chunk;
      });
      const exited = new Promise<number | null>((resolve) =>
        child.on("exit", resolve),
      );
      try {
        const deadline = Date.now() + 10_000;
        while (!output.includes("agent_started")) {
          assert.equal(child.exitCode, null, errors);
          assert.ok(Date.now() < deadline, "agent did not start");
          await setTimeout(10);
        }
        child.kill(signal);
        assert.equal(await exited, 130, errors);
        assert.equal(events(output).at(-1).data.reason, "interrupted");
      } finally {
        if (child.exitCode === null) child.kill("SIGKILL");
      }
    },
  );
}

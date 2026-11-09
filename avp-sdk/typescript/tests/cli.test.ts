import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { setTimeout } from "node:timers/promises";
import { main, trajectorySink } from "../src/agent_cli.js";
import { Recorder } from "../src/recorder.js";
import { parseTrajectory, avpMetadata } from "../src/trajectory.js";

const fixture = new URL("./fixtures/agent.js", import.meta.url);
const commission = (prompt: string) =>
  JSON.stringify({
    avp_version: "0.1",
    run_id: "r",
    prompt,
    model: { provider: "p", id: "m" },
  });
const document = (text: string) => parseTrajectory(text);
const cli = (...argv: string[]) =>
  spawnSync(process.execPath, [fixture.pathname, ...argv], {
    encoding: "utf8",
  });

test("CLI writes complete and refused trajectories, with paths or inline JSON", async () => {
  const dir = await mkdtemp(join(tmpdir(), "avp-cli-"));
  try {
    const c = join(dir, "commission.json");
    const out = join(dir, "trajectory.json");
    await writeFile(c, commission("Hi"));
    await writeFile(out, "old contents");
    const result = cli("run", "--commission", c, "--out", out);
    assert.equal(result.status, 0, result.stderr);
    const written = document(await readFile(out, "utf8"));
    assert.equal(written.schema_version, "ATIF-v1.8");
    assert.equal(avpMetadata(written).stop_reason, "converged");
    assert.equal(written.steps.at(-1)?.message, "Hello.");
    assert.equal(
      cli("run", "--commission", commission("Hi"), "--out", "-").status,
      0,
    );
    await writeFile(c, "not JSON");
    const refusal = cli("run", "--commission", c, "--out", "-");
    assert.equal(refusal.status, 0, refusal.stderr);
    assert.equal(avpMetadata(document(refusal.stdout)).stop_reason, "error");
    assert.equal(JSON.parse(cli("describe").stdout).agent_name, "example");
    assert.deepEqual(JSON.parse(cli("ping").stdout), {
      type: "pong",
      avp_version: "0.1",
    });
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
    const path = join(dir, "trajectory.json");
    const archive = join(dir, "archived.json");
    const rec = new Recorder(trajectorySink(path));
    await rec.start({ prompt: "Hi", model: { provider: "p", id: "m" } });
    await rename(path, archive);
    await rec.stop("converged");
    assert.equal(
      avpMetadata(document(await readFile(archive, "utf8"))).complete,
      false,
    );
    assert.equal(
      avpMetadata(document(await readFile(path, "utf8"))).complete,
      true,
    );
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
        while (!errors.includes("ready")) {
          assert.equal(child.exitCode, null, errors);
          assert.ok(Date.now() < deadline, "agent did not start");
          await setTimeout(10);
        }
        child.kill(signal);
        assert.equal(await exited, 130, errors);
        assert.equal(avpMetadata(document(output)).stop_reason, "interrupted");
      } finally {
        if (child.exitCode === null) child.kill("SIGKILL");
      }
    },
  );
}

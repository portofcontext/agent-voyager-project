import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  rmSync,
  readdirSync,
  symlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { Recorder } from "../src/recorder.js";
import { trajectorySink } from "../src/agent_cli.js";
import { captureStart, parseAgentStart } from "../src/agent_start.js";
import { avpMetadata, type Recording } from "../src/trajectory.js";
import type { Commission } from "../src/commission.js";

const cases = JSON.parse(
  readFileSync(
    new URL("../../../testdata/agent-start.json", import.meta.url),
    "utf8",
  ),
);
for (const c of cases)
  test(`Agent Start: ${c.name}`, () => {
    if (c.valid) parseAgentStart(c.document);
    else assert.throws(() => parseAgentStart(c.document));
  });

test("four documents preserve complete start configuration without extracting skill copies", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-start-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const skill = join(root, "skill"),
    directory = join(root, "run");
  mkdirSync(join(skill, "references"), { recursive: true });
  const original =
    "---\nname: research\ndescription: Research.\n---\nRead references.\r\n";
  writeFileSync(join(skill, "SKILL.md"), original);
  const binary = Buffer.from([0, 255, 13, 10]);
  writeFileSync(join(skill, "references/data.bin"), binary);
  const snapshots: Recording[] = [],
    publish = trajectorySink(join(directory, "trajectory.json"));
  const rec = new Recorder(
    async (snapshot) => {
      await publish(snapshot);
      snapshots.push(snapshot);
    },
    { runId: "r" },
  );
  const commission: Commission = {
    avp_version: "0.1",
    run_id: "r",
    prompt: "research",
    model: { provider: "test", id: "requested" },
    mcp_servers: [{ id: "math", type: "stdio", command: ["math-server"] }],
    output_schema: { type: "object" },
  };
  mkdirSync(directory);
  const suppliedJson = { ...commission, system_prompt: null };
  writeFileSync(
    join(directory, "commission.json"),
    JSON.stringify(suppliedJson),
  );
  await rec.begin(commission, {
    avp_version: "0.1",
    agent_name: "test",
    agent_version: "1",
  });
  assert.ok(!readdirSync(directory).includes("agent-start.json"));
  const selected = {
    name: "research",
    description: "Research.",
    source: pathToFileURL(skill).href,
  };
  await rec.start({
    prompt: "research",
    system_prompt: "",
    model: { provider: "test", id: "resolved" },
    skills: [selected],
    subagents: [{ name: "child", skills: [selected] }],
    mcp_servers: [{ id: "math", status: "connected" }],
  });
  writeFileSync(join(skill, "SKILL.md"), "changed during the run");
  await rec.response([
    {
      type: "text",
      text: "42",
      citations: [{ type: "url", source_url: "https://example.com" }],
    },
  ]);
  await rec.stop("converged", { answer: 42 });
  assert.deepEqual(readdirSync(directory).sort(), [
    "agent-start.json",
    "commission.json",
    "descriptor.json",
    "trajectory.json",
  ]);
  const start = parseAgentStart(
    readFileSync(join(directory, "agent-start.json"), "utf8"),
  );
  assert.equal(start.model.id, "resolved");
  assert.equal(start.system_prompt, "");
  assert.deepEqual(start.output_schema, { type: "object" });
  assert.equal(start.skills![0].files!["SKILL.md"], original);
  const captured = start.skills![0].files!["references/data.bin"];
  assert.ok(typeof captured === "object");
  assert.deepEqual(Buffer.from(captured.base64, "base64"), binary);
  assert.deepEqual(
    start.subagents![0].skills![0].files,
    start.skills![0].files,
  );
  assert.deepEqual(start.mcp_servers![0], {
    id: "math",
    type: "stdio",
    command: ["math-server"],
    status: "connected",
  });
  assert.deepEqual(
    JSON.parse(readFileSync(join(directory, "commission.json"), "utf8")),
    suppliedJson,
  );
  assert.equal(
    avpMetadata(snapshots.at(-1)!.trajectory.agent).skills,
    undefined,
  );
  assert.match(
    readFileSync(join(directory, "trajectory.json"), "utf8"),
    /citations/,
  );
  await publish(snapshots.at(-1)!);
});

test("selected inline, body-only, and metadata-only skills retain their distinctions", () => {
  const commission: Commission = {
    avp_version: "0.1",
    run_id: "r",
    prompt: "task",
    model: { provider: "test", id: "m" },
    skills: [
      {
        name: "supplied",
        files: { "SKILL.md": "instructions", "support.txt": "support" },
      },
      { name: "unused", files: { "SKILL.md": "unused" } },
    ],
  };
  const start = captureStart(
    {
      prompt: "task",
      model: commission.model,
      skills: [
        { name: "supplied", description: "selected" },
        {
          name: "body",
          description: "body only",
          files: { "instructions.md": "body" },
        },
        { name: "opaque", description: "no files exposed" },
      ],
    },
    commission,
    "r",
  );
  assert.deepEqual(start.skills![0].files, commission.skills![0].files);
  assert.deepEqual(start.skills![1].files, { "instructions.md": "body" });
  assert.equal(start.skills![2].files, undefined);
  assert.equal(start.skills!.length, 3);
});

test("unreadable and symlinked skill directories fail capture", (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-start-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const context = {
    prompt: "task",
    model: { provider: "test", id: "m" },
    skills: [{ name: "s", description: "s", source: pathToFileURL(root).href }],
  };
  assert.throws(() => captureStart(context, undefined, "r"), /SKILL.md/);
  writeFileSync(join(root, "SKILL.md"), "skill");
  symlinkSync(join(root, "SKILL.md"), join(root, "link"));
  assert.throws(() => captureStart(context, undefined, "r"), /regular files/);
});

test("images remain ATIF files and cannot overwrite run documents or escape", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-start-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const snapshots: Recording[] = [];
  const rec = new Recorder(
    async (s) => {
      snapshots.push(s);
    },
    { runId: "r" },
  );
  await rec.start({ prompt: "task", model: { provider: "test", id: "m" } });
  await rec.response([
    {
      type: "image",
      source: {
        type: "base64",
        media_type: "image/png",
        data: Buffer.from("image bytes").toString("base64"),
      },
    },
  ]);
  await rec.stop("converged");
  const snapshot = snapshots.at(-1)!;
  await trajectorySink(join(root, "trajectory.json"))(snapshot);
  assert.equal(
    readFileSync(join(root, [...snapshot.assets.keys()][0]), "utf8"),
    "image bytes",
  );
  await assert.rejects(
    trajectorySink(join(root, "agent-start.json"))(snapshot),
    /conflicts/,
  );
  writeFileSync(join(root, "agent-start.json"), '{"run_id":"other"}');
  await assert.rejects(trajectorySink(join(root, "trajectory.json"))(snapshot));
  snapshot.assets.set("../escape", Buffer.from("no"));
  await assert.rejects(
    trajectorySink(join(root, "other/trajectory.json"))(snapshot),
  );
});

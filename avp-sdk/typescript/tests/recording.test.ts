import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  rmSync,
  readdirSync,
  symlinkSync,
  renameSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { Recorder } from "../src/recorder.js";
import { trajectorySink } from "../src/agent_cli.js";
import {
  avpMetadata,
  parseTrajectory,
  type Recording,
  type Agent,
} from "../src/trajectory.js";
const agent: Agent = {
  name: "test",
  version: "1",
  model_name: "m",
  extra: { avp: { model: { provider: "test" } } },
};

test("a trajectory references immutable skill files, including subagent skills", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-recording-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const skill = join(root, "skill"),
    directory = join(root, "run");
  mkdirSync(join(skill, "references"), { recursive: true });
  const original =
    "---\nname: research\ndescription: Research.\n---\nRead references.\r\n";
  const binary = Buffer.from([0, 255, 13, 10]);
  writeFileSync(join(skill, "SKILL.md"), original);
  writeFileSync(join(skill, "references/data.bin"), binary);
  const recordings: Recording[] = [];
  const rec = new Recorder(
    async (recording) => {
      recordings.push(recording);
    },
    { runId: "r" },
  );
  const selected = {
    name: "research",
    description: "Research.",
    source: pathToFileURL(skill).href,
  };
  const configured = structuredClone(agent);
  configured.extra!.avp!.skills = [selected];
  configured.extra!.avp!.subagents = [{ name: "child", skills: [selected] }];
  await rec.start(configured, "research", { systemPrompt: "" });
  writeFileSync(join(skill, "SKILL.md"), "changed during the run");
  await rec.step([
    {
      type: "text",
      text: "42",
      citations: [{ type: "url", source_url: "https://example.com" }],
    },
  ]);
  await rec.stop("converged", { answer: 42 });
  assert.equal(recordings.length, 1);
  const recording = recordings[0];
  await trajectorySink(join(directory, "trajectory.json"))(recording);
  assert.deepEqual(readdirSync(directory).sort(), [
    "skills",
    "trajectory.json",
  ]);
  const extra = avpMetadata(recording.trajectory.agent);
  assert.equal(extra.skills[0].source, "file:skills/0-research");
  assert.equal(
    extra.subagents[0].skills[0].source,
    "file:skills/subagent-0/0-research",
  );
  assert.equal(
    readFileSync(join(directory, "skills/0-research/SKILL.md"), "utf8"),
    original,
  );
  for (const path of ["skills/0-research", "skills/subagent-0/0-research"])
    assert.deepEqual(
      readFileSync(join(directory, path, "references/data.bin")),
      binary,
    );
  renameSync(directory, join(root, "moved"));
  const moved = join(root, "moved");
  const saved = parseTrajectory(
    readFileSync(join(moved, "trajectory.json"), "utf8"),
  );
  const file = join(
    moved,
    avpMetadata(saved.agent).skills[0].source.slice(5),
    "SKILL.md",
  );
  assert.equal(readFileSync(file, "utf8"), original);
  writeFileSync(file, "changed");
  await assert.rejects(
    trajectorySink(join(moved, "trajectory.json"))(recording),
    /different content/,
  );
});

test("unreadable and symlinked skill directories fail capture", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-recording-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const configured = structuredClone(agent);
  configured.extra!.avp!.skills = [
    { name: "s", description: "s", source: pathToFileURL(root).href },
  ];
  const rec = new Recorder(async () => {});
  await assert.rejects(rec.start(configured, "task"), /SKILL.md/);
  writeFileSync(join(root, "SKILL.md"), "skill");
  symlinkSync(join(root, "SKILL.md"), join(root, "link"));
  await assert.rejects(rec.start(configured, "task"), /regular files/);
});

test("images remain ATIF files and cannot replace the trajectory or escape", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-recording-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const recordings: Recording[] = [];
  const rec = new Recorder(async (s) => {
    recordings.push(s);
  });
  await rec.start(agent, "task");
  const image = rec.image(Buffer.from("image bytes"), "image/png");
  await rec.step([image]);
  await rec.stop("converged");
  const recording = recordings[0];
  await trajectorySink(join(root, "trajectory.json"))(recording);
  assert.equal(readFileSync(join(root, image.path), "utf8"), "image bytes");
  recording.assets.set("trajectory.json", Buffer.from("no"));
  await assert.rejects(
    trajectorySink(join(root, "trajectory.json"))(recording),
    /replace/,
  );
  recording.assets.delete("trajectory.json");
  recording.assets.set("../escape", Buffer.from("no"));
  await assert.rejects(
    trajectorySink(join(root, "other/trajectory.json"))(recording),
  );
});

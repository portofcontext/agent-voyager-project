import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  rmSync,
  symlinkSync,
  unlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { Recorder } from "../src/recorder.js";
import { trajectorySink } from "../src/agent_cli.js";
import {
  parseArtifacts,
  writeArtifacts,
  readArtifacts,
} from "../src/artifacts.js";
import { avpMetadata, type Recording } from "../src/trajectory.js";

const cases = JSON.parse(
  readFileSync(
    new URL("../../../testdata/artifacts.json", import.meta.url),
    "utf8",
  ),
);
for (const c of cases)
  test(`artifact manifest: ${c.name}`, () => {
    if (c.valid) parseArtifacts(c.manifest);
    else assert.throws(() => parseArtifacts(c.manifest));
  });

test("captures full immutable skill inputs and output files while trace metadata stays inline", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-artifacts-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const skill = join(root, "native-skill"),
    directory = join(root, "run");
  mkdirSync(join(skill, "references"), { recursive: true });
  writeFileSync(join(skill, "SKILL.md"), "original instructions");
  const bytes = Buffer.from([0, 255, 13, 10]);
  writeFileSync(join(skill, "references/data.bin"), bytes);
  const snapshots: Recording[] = [],
    publish = trajectorySink(join(directory, "trajectory.json"));
  const rec = new Recorder(
    async (snapshot) => {
      await publish(snapshot);
      readArtifacts(directory, "r");
      snapshots.push(snapshot);
    },
    { runId: "r" },
  );
  await rec.begin(
    {
      avp_version: "0.1",
      run_id: "r",
      prompt: "research",
      model: { provider: "test", id: "m" },
    },
    { avp_version: "0.1", agent_name: "test", agent_version: "1" },
  );
  await rec.start({
    prompt: "research",
    model: { provider: "test", id: "m" },
    skills: [
      {
        name: "research",
        description: "Research.",
        source: pathToFileURL(skill).href,
      },
    ],
  });
  writeFileSync(join(skill, "SKILL.md"), "revised instructions");
  await rec.artifact(
    "outputs/skills/research/SKILL.md",
    readFileSync(join(skill, "SKILL.md")),
    "output",
  );
  const arbitrary = { extra: { avp: { annotations: { unchanged: true } } } };
  await rec.response([
    { type: "tool_use", id: "c", name: "echo", input: arbitrary },
    {
      type: "text",
      text: "hi",
      citations: [{ type: "url", source_url: "https://example.com" }],
    },
  ]);
  await rec.toolReturned("c", "ok");
  await rec.stop("converged", { answer: 42 });
  assert.equal(
    readFileSync(join(directory, "inputs/skills/research/SKILL.md"), "utf8"),
    "original instructions",
  );
  assert.deepEqual(
    readFileSync(join(directory, "inputs/skills/research/references/data.bin")),
    bytes,
  );
  assert.equal(
    JSON.parse(
      readFileSync(join(directory, "inputs/effective-agent.json"), "utf8"),
    ).skills[0].source,
    "file:inputs/skills/research",
  );
  const final = snapshots.at(-1)!.trajectory,
    step = final.steps.at(-1)!;
  assert.equal(avpMetadata(final.agent).skills, undefined);
  assert.deepEqual(step.tool_calls![0].arguments, arbitrary);
  assert.deepEqual(
    avpMetadata(step).message_metadata[0].annotations.citations,
    [{ type: "url", source_url: "https://example.com" }],
  );
  const trace = readFileSync(join(directory, "trajectory.json"), "utf8");
  assert.match(trace, /citations/);
  assert.doesNotMatch(trace, /details_path/);
  assert.ok(
    readArtifacts(directory).artifacts.every(
      (a) => !a.path.startsWith("outputs/details/"),
    ),
  );
  assert.deepEqual(avpMetadata(final).output, { answer: 42 });
  assert.ok(
    readArtifacts(directory).artifacts.every(
      (a) => a.path !== "outputs/result.json",
    ),
  );
});

test("rejects hash changes, missing files, overwrites, and escaping symlinks", (t) => {
  const root = mkdtempSync(join(tmpdir(), "avp-artifact-integrity-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const directory = join(root, "run");
  mkdirSync(directory);
  writeArtifacts(
    directory,
    "r",
    new Map([
      ["inputs/x.bin", { role: "input", content: Buffer.from("hello") }],
    ]),
  );
  readArtifacts(directory, "r");
  assert.throws(() => readArtifacts(directory, "other"), /different run/);
  assert.throws(
    () => writeArtifacts(directory, "other", new Map()),
    /different run/,
  );
  assert.throws(() => writeArtifacts(directory, "r", new Map()), /immutable/);
  assert.throws(
    () =>
      writeArtifacts(
        directory,
        "r",
        new Map([
          ["inputs/x.bin", { role: "output", content: Buffer.from("hello") }],
        ]),
      ),
    /immutable/,
  );
  assert.throws(
    () =>
      writeArtifacts(
        directory,
        "r",
        new Map([
          ["inputs/x.bin", { role: "input", content: Buffer.from("changed") }],
        ]),
      ),
    /different content/,
  );
  writeFileSync(join(directory, "inputs/x.bin"), "tampered");
  assert.throws(() => readArtifacts(directory), /hash mismatch/);
  unlinkSync(join(directory, "inputs/x.bin"));
  assert.throws(() => readArtifacts(directory), /ENOENT/);
  const escaped = join(root, "escaped");
  mkdirSync(escaped);
  symlinkSync(root, join(escaped, "escape"));
  assert.throws(
    () =>
      writeArtifacts(
        escaped,
        "r",
        new Map([
          ["escape/outside", { role: "output", content: Buffer.from("no") }],
        ]),
      ),
    /escapes/,
  );
});

import assert from "node:assert/strict";
import test from "node:test";
import { parseCommission } from "../src/commission.js";
import { parseDescriptor } from "../src/descriptor.js";
import { checkCommission } from "../src/utils/preflight.js";

const descriptor = parseDescriptor({
  avp_version: "0.1",
  agent_name: "demo",
  agent_version: "1.2.0",
  tools: [
    { name: "bash", inputSchema: { type: "object" } },
    { name: "search", inputSchema: { type: "object" }, mcp_server_id: "web" },
  ],
  mcp_servers: [{ id: "web" }],
  skills: [{ name: "review", description: "Reviews code." }],
  subagents: [{ name: "explorer" }],
});
const commission = (fields: Record<string, unknown> = {}) =>
  parseCommission({
    avp_version: "0.1",
    run_id: "r",
    prompt: "Hi",
    model: { provider: "p", id: "m" },
    ...fields,
  });
const skill = (text: string, name = "lint") => ({
  name,
  files: { "SKILL.md": text },
});

test("Commission refusal checks use Python's order and messages", () => {
  assert.equal(checkCommission(commission(), descriptor), undefined);
  assert.equal(
    checkCommission(commission({ agents: {} }), descriptor),
    "agents has no entry for 'demo'",
  );
  assert.equal(
    checkCommission(
      commission({ agents: { demo: { version: "1.1.0" } } }),
      descriptor,
    ),
    "agents.demo.version is '1.1.0', but this agent is version '1.2.0'",
  );
  for (const [field, known, unknown] of [
    ["enabled_tools", "bash", "search"],
    ["enabled_subagents", "explorer", "planner"],
    ["enabled_skills", "review", "deploy"],
    ["enabled_mcp_servers", "web", "db"],
  ]) {
    assert.equal(
      checkCommission(
        commission({ agents: { demo: { [field]: [known] } } }),
        descriptor,
      ),
      undefined,
    );
    assert.equal(
      checkCommission(
        commission({ agents: { demo: { [field]: [known, unknown] } } }),
        descriptor,
      ),
      `agents.demo.${field} names items the agent doesn't have: ${unknown}`,
    );
  }
  assert.equal(
    checkCommission(
      commission({
        mcp_servers: [
          { id: "web", type: "http", url: "https://example.com/mcp" },
        ],
      }),
      descriptor,
    ),
    "MCP server 'web' has the same id as one the agent comes with",
  );
  assert.equal(
    checkCommission(
      commission({ skills: [skill("---\nname: review\n---\n", "review")] }),
      descriptor,
    ),
    "skill 'review' has the same name as one the agent comes with",
  );
});

test("skill frontmatter follows the Python helper's quotes, comments, and block values", () => {
  for (const text of [
    "---\nname: lint\n---\n",
    '---\nname: "lint"\n---\n',
    "---\r\nname: 'lint'\r\n---\r\n",
    "---\nname:\tlint # comment\n---\n",
    "---\nname: >\n  lint\n---\n",
    "---\nname: |\n  lint\n---\n",
  ]) {
    assert.equal(
      checkCommission(commission({ skills: [skill(text)] }), descriptor),
      undefined,
    );
  }
  assert.equal(
    checkCommission(
      commission({ skills: [skill("---\nname: linter\n---\n")] }),
      descriptor,
    ),
    "skill 'lint': the frontmatter of its SKILL.md names 'linter'",
  );
  for (const text of [
    "name: lint\n",
    "---\ndescription: Lints\n---\n",
    "---\nmetadata:\n  name: lint\n---\n",
  ]) {
    assert.equal(
      checkCommission(commission({ skills: [skill(text)] }), descriptor),
      "skill 'lint': the frontmatter of its SKILL.md has no name",
    );
  }
});

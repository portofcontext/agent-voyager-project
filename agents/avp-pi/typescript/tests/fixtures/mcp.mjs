/** A stdio MCP boundary for structured results and environment references. */
import { createInterface } from "node:readline";
const tools = [
  {
    name: "Echo",
    description: "Return the configured test value.",
    inputSchema: { type: "object", properties: {} },
    outputSchema: {
      type: "object",
      properties: { value: { type: "string" } },
      required: ["value"],
    },
  },
];
for await (const line of createInterface({ input: process.stdin })) {
  const request = JSON.parse(line);
  if (request.id === undefined) continue;
  let result;
  if (request.method === "initialize")
    result = {
      protocolVersion: request.params.protocolVersion,
      capabilities: { tools: {} },
      serverInfo: { name: "structured-fixture", version: "1" },
    };
  else if (request.method === "tools/list") result = { tools };
  else if (request.method === "tools/call")
    result = {
      content: [{ type: "text", text: "STRUCTURED" }],
      structuredContent: {
        value: process.env.AVP_TEST_MCP_CREDENTIAL ?? "missing",
      },
    };
  else result = {};
  process.stdout.write(
    JSON.stringify({ jsonrpc: "2.0", id: request.id, result }) + "\n",
  );
}

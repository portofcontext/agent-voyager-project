#!/usr/bin/env node
/** Keep ping independent of the native runtime. */
import { main } from "@agent-voyager-project/sdk/agent_cli";
process.exitCode = await main({
  describe: async () => (await import("./descriptor.js")).describe(),
  run: async (received, sink, signal) =>
    (await import("./agent.js")).run(received, sink, { signal }),
});

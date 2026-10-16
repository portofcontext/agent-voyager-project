#!/usr/bin/env node
/**
 * Agent entrypoint (`ping` / `describe` / `run`), via the stock agent CLI.
 * The adapter loads lazily so `ping` never imports Pi.
 */
import { main } from "@avp/types/agent-cli";

process.exitCode = await main({
  describe: async () => (await import("./agent.js")).describe(),
  run: async (commission, sink, signal) => (await import("./agent.js")).run(commission, sink, { signal }),
});

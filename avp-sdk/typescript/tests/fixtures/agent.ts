import { setTimeout } from "node:timers/promises";
import { main } from "../../src/agent_cli.js";
import { parseDescriptor } from "../../src/descriptor.js";
import { Recorder } from "../../src/recorder.js";
import { planRun } from "../../src/utils/run_plan.js";

const describe = () =>
  parseDescriptor({
    avp_version: "0.1",
    agent_name: "example",
    agent_version: "0.1.0",
  });
process.exitCode = await main({
  describe,
  run: async (received, sink, signal) => {
    const rec = new Recorder(sink);
    const descriptor = describe();
    const commission = await rec.begin(received, descriptor);
    if (!commission) return;
    const plan = planRun(commission, descriptor);
    await rec.start(plan.agent, plan.prompt, {
      systemPrompt: plan.system_prompt,
    });
    if (commission.prompt === "crash") throw new Error("fixture crash");
    if (commission.prompt === "wait") {
      process.stderr.write("ready\n");
      try {
        await setTimeout(60_000, undefined, { signal });
      } catch (error) {
        await rec.stop("interrupted");
        throw error;
      }
    }
    await rec.step([{ type: "text", text: "Hello." }]);
    await rec.stop("converged", "Hello.");
  },
});

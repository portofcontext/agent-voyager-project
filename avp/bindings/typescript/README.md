# @avp/types: TypeScript types and Recorder for the AVP wire format

```bash
npm install github:portofcontext/agent-voyager-project#main --save
```

(Not yet on npm. Vendor by git path until v0.1 stabilizes.)

## What's here

Generated TypeScript types for the AVP v0.1 wire format. Three modules, one per
data-shape spec (`commission`, `trajectory`, `agent-descriptor`):

```typescript
import type { Commission, Event } from "@avp/types";

const event: Event = JSON.parse(line);

switch (event.type) {
  case "avp.agent_started": {
    console.log(event.subject);
    break;
  }
  case "avp.assistant_message": {
    const cost = event.data["avp.cost_usd"];
    const source = event.data["avp.cost.source"]; // "computed" | "reported" | "unknown"
    break;
  }
  case "avp.tool_returned": {
    console.log(event.data["avp.tool.name"]);
    break;
  }
  // ...
}
```

Sub-path imports for the helper types:

```typescript
import type { McpServerHttp, McpServerStdio } from "@avp/types/commission";
import type { AssistantMessageEvent, AgentStartedData } from "@avp/types/trajectory";
```

## Recorder

Adapters for TypeScript runtimes report what their harness did to a `Recorder`,
which owns span minting, step numbering, turn buffering, tool pairing,
subagent frames, and cost. It mirrors the Python and Rust Recorders and runs
the same shared vectors
(`avp/core/conformance/src/avp_conformance/recorder/v0.1/`).

```typescript
import { FileSink, Recorder, loadDefaultPrices } from "@avp/types";

const rec = new Recorder(new FileSink(out), {
  runId: commission.run_id,
  provider: "anthropic",
  prices: loadDefaultPrices(),
});
rec.prelude(commission, descriptor);              // run_requested, agent_described
rec.start({ requestModel, tools });               // agent_started
rec.assistant(content, usage, { model });         // assistant_message + tool_invoked
rec.toolResult("call_1", "ok");                   // tool_returned
rec.stop("converged");                            // agent_stopped
```

Invalid reports (unknown or duplicate call ids, mismatched usage, reports after
`stop`) throw `RecorderError` and leave the Recorder's state intact.
`loadDefaultPrices()` reads the canonical table from the Python package in this
repository, so the binding is used from a checkout (a `file:` dependency).

## Source of truth

- `avp/bindings/python/src/avp/{commission,descriptor,trajectory}.py` (Pydantic, hand-written)
  -> `avp/core/spec/v0.1/*.schema.json` (auto-generated; `avp/scripts/generate-schemas.py`)
  -> `avp/bindings/typescript/src/*.ts` (generated here, via `json-schema-to-typescript`)

Don't edit `src/{commission,trajectory,agent-descriptor}.ts` by hand; they're regenerated. Edit the Python sources upstream. `recorder.ts`, `pricing.ts`, `sink.ts`, and `ids.ts` are hand-written.

## Regenerating

```bash
make bindings           # regenerate from current schemas
make bindings-check     # CI drift check (fails if generated code is stale)
make bindings-test      # smoke tests for both Rust and TS
```

## Build / test

```bash
npm install
npm run typecheck       # tsc --noEmit
npm run build           # tsc → dist/
npm test                # node --test: round-trips, helpers, shared Recorder vectors
```

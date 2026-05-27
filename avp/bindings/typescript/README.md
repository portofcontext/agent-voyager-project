# @avp/types — TypeScript types for the AVP wire format

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

## Source of truth

- `avp/bindings/python/src/avp/{commission,descriptor,trajectory}.py` (Pydantic, hand-written)
  -> `avp/core/spec/v0.1/*.schema.json` (auto-generated; `avp/scripts/generate-schemas.py`)
  -> `avp/bindings/typescript/src/*.ts` (generated here, via `json-schema-to-typescript`)

Don't edit `src/{commission,event}.ts` by hand — they're regenerated. Edit the Python sources upstream.

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
npm test                # node --test against dist-test/
```

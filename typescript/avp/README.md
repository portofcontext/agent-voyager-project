# @avp/types — TypeScript types for the AVP wire format

```bash
npm install github:portofcontext/agent-execution-protocol#main --save
```

(Not yet on npm. Vendor by git path until v0.1 stabilizes.)

## What's here

Generated TypeScript types for the AVP v0.1 wire format. Two modules, one per top-level message class:

```typescript
import type { Commission, Event } from "@avp/types";

const event: Event = JSON.parse(line);

switch (event.type) {
  case "avp.agent_started": {
    console.log(event.subject);
    break;
  }
  case "avp.model_turn_ended": {
    const cost = event.data["avp.cost_usd"];
    const source = event.data["avp.cost.source"]; // "computed" | "reported" | "unknown"
    break;
  }
  case "avp.refusal_recorded": {
    console.log(event.data["avp.refusal.reason"]);
    break;
  }
  // ...
}
```

Sub-path imports for the helper types:

```typescript
import type { Tool, McpServer } from "@avp/types/commission";
import type { ModelTurnEndedEvent, AgentStartedData } from "@avp/types/event";
```

## Source of truth

- `python/avp/src/avp/types.py` (Pydantic, hand-written)
  → `spec/v0.1/*.schema.json` (auto-generated; `scripts/generate-schemas.py`)
  → `typescript/avp/src/*.ts` (generated here, via `json-schema-to-typescript`)

Don't edit `src/{commission,event}.ts` by hand — they're regenerated. Edit `types.py` upstream.

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

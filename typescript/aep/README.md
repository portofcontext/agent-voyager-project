# @aep/types — TypeScript types for the AEP wire format

```bash
npm install github:portofcontext/agent-execution-protocol#main --save
```

(Not yet on npm. Vendor by git path until v0.1 stabilizes.)

## What's here

Generated TypeScript types for the AEP v0.1 wire format. Three modules, one per top-level message class:

```typescript
import type { Config, Event, SupervisorMessage } from "@aep/types";

const event: Event = JSON.parse(line);

switch (event.type) {
  case "aep.agent_started": {
    console.log(event.subject);
    break;
  }
  case "aep.model_turn_ended": {
    const cost = event.data["aep.cost_usd"];
    const source = event.data["aep.cost.source"]; // "computed" | "reported" | "unknown"
    break;
  }
  case "aep.refusal_recorded": {
    console.log(event.data["aep.refusal.reason"]);
    break;
  }
  // ...
}
```

Sub-path imports for the helper types:

```typescript
import type { Verifier, McpServer } from "@aep/types/config";
import type { ModelTurnEndedEvent, AgentStartedData } from "@aep/types/event";
import type { ToolExecResolvedEvent } from "@aep/types/supervisor-message";
```

## Source of truth

- `python/aep/src/aep/types.py` (Pydantic, hand-written)
  → `spec/v0.1/*.schema.json` (auto-generated; `scripts/generate-schemas.py`)
  → `typescript/aep/src/*.ts` (generated here, via `json-schema-to-typescript`)

Don't edit `src/{config,event,supervisor-message}.ts` by hand — they're regenerated. Edit `types.py` upstream.

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

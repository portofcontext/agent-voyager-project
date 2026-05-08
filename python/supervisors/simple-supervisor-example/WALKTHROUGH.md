# Anatomy of a DDD self-correcting run

A trace of `examples/04_ddd_supervisor.py` against a live Claude Haiku, the day
the inject_correction loop did its job. This is what AVP looks like when
every piece works together.

> The point of this walkthrough isn't "the agent wrote good code." It's that
> the agent wrote BAD code, the supervisor caught it via a deterministic
> verifier, the supervisor's domain knowledge nudged the agent through the
> trajectory, and the agent self-corrected to a DDD-faithful design — all
> recorded on the wire as facts a non-technical reviewer can read top to
> bottom.

## The setup

**Workspace** (`examples/04_ddd_domain/`): a small but real DDD codebase.

```
domain/
  order/
    order.py            # Aggregate root
    order_line.py       # Value object — frozen, validates unit_price >= 0
    order_status.py
  customer/
    customer.py
    email_address.py
tests/invariants/
  test_order_invariants.py    # 14 invariant tests
  test_customer_invariants.py # 6 invariant tests
```

20 invariant tests pass on the clean baseline.

**Supervisor profile** (`DDD_STRICT`): three verifiers compiling DDD concerns.

| Verifier | Trigger | on_failure | What it enforces |
|---|---|---|---|
| `domain-layer-purity` | `on_tool:write_file` | `halt` | No infrastructure imports in `domain/` |
| `aggregate-invariants` | `after_each_turn` | `inject_correction` | `pytest tests/invariants/` passes |
| `no-anemic-suffixes-in-domain` | `on_tool:write_file` | `inject_correction` | No `*Manager.py` / `*Helper.py` / `*Util.py` in `domain/` |

The first one halts (architectural contract — non-recoverable in one run).
The other two inject corrections (the agent gets to retry).

**Boundary**: $1.50, 15 turns, 200K tokens.

**The task** (intentionally ambiguous):

> Add a method `apply_discount(amount: Decimal) -> None` to the Order aggregate. It MUST:
>   - Reject discounts greater than the current total (raise ValueError).
>   - Reject discounts on non-PENDING orders (raise ValueError).
>   - Otherwise, append a synthetic OrderLine with sku='DISCOUNT', quantity=1, and a NEGATIVE unit_price equal to -amount, so that Order.total still equals sum(line.subtotal for line in lines).

The bait: the prompt says use a NEGATIVE unit_price. The existing `OrderLine`
value object validates `unit_price >= 0`. There's a real DDD choice the agent
has to make — weaken the invariant, or restructure the feature.

## The trace

### Turns 1–3 — investigation

The agent reads the domain, the order files, the existing tests. Three
`aggregate-invariants` PASSes. No surprises.

### Turn 4 — the wrong move

The agent edits `domain/order/order_line.py`, removing the
`unit_price >= 0` validation. This unblocks the literal task as written
(allow negative prices for discount lines).

```
[turn 4] -> write_file(['path', 'content']) path=domain/order/order_line.py
[turn 4] verifier 'domain-layer-purity': PASS
[turn 4] verifier 'no-anemic-suffixes-in-domain': PASS
[turn 4] verifier 'aggregate-invariants': FAIL
    stdout: ..................F.   [100%]
    Failed: DID NOT RAISE <class 'ValueError'>
```

The two write-time verifiers pass — the change didn't add infrastructure
imports and didn't introduce a Manager.py. But after the turn ends, the
test suite runs and catches that
`test_order_line_unit_price_must_be_non_negative` no longer raises. **The
existing invariant is broken.**

The supervisor's correction injects into the conversation:

> An aggregate invariant regressed — the test suite under tests/invariants/
> now has a failing test. Important: don't loosen the existing invariant to
> fit the new feature. The FEATURE has to fit the invariant, not the other
> way around. Re-examine: is there a different shape — a new value object,
> a separate field on the aggregate, a different state transition — that
> preserves what the invariant was protecting? Revert the
> invariant-weakening change and try again with a design that doesn't
> require breaking it.

### Turns 5–6 — friction

The agent reaches for `bash` to debug rather than reading the correction.
It tries some commands (one with a hallucinated path), the verifier keeps
failing. Two more `aggregate-invariants` FAILs. **~$0.01 of wasted turns.**

This is honest: real model behavior includes confusion. The supervisor
keeps presenting the same correction every turn until the agent acts.

### Turn 7 — recovery

The agent rewrites `domain/order/order_line.py`, restoring the
`unit_price >= 0` validation. Verifier passes.

```
[turn 7] -> write_file(['path', 'content']) path=domain/order/order_line.py
[turn 7] verifier 'domain-layer-purity': PASS
[turn 7] verifier 'no-anemic-suffixes-in-domain': PASS
[turn 7] verifier 'aggregate-invariants': PASS
```

The agent has internalized the principle. Time to find a different shape.

### Turn 8 — the DDD-correct design

The agent rewrites `domain/order/order.py` adding a SEPARATE field for
discounts on the aggregate, instead of breaking the OrderLine value object.

```python
@dataclass
class Order:
    id: str
    customer_id: str
    lines: list[OrderLine] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    discount: Decimal = field(default_factory=lambda: Decimal("0"))   # NEW

    @property
    def subtotal(self) -> Decimal:
        return sum((line.subtotal for line in self.lines), Decimal("0"))

    @property
    def total(self) -> Decimal:
        return self.subtotal - self.discount     # invariant preserved

    def apply_discount(self, amount: Decimal) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError(...)
        if amount < Decimal("0"):
            raise ValueError(...)
        if amount > self.subtotal:
            raise ValueError(...)
        self.discount = amount
```

This is **textbook DDD**:

1. The discount is a property of the aggregate, not a synthetic line item.
2. `OrderLine`'s value-object invariant is preserved (still `unit_price >= 0`).
3. `apply_discount` lives ON the aggregate, not in a `OrderDiscountManager`.
4. The math invariant (total reflects the lines) holds with a clean redefinition.
5. New invariants are encoded as runtime checks in `apply_discount`.

All three verifiers pass.

### Turns 9–15 — verification + tests

The agent runs the test suite to confirm. Reads files. Adds two new tests
to `tests/invariants/test_order_invariants.py`:

- A happy-path test (apply 5.50 discount, total = 25.50 - 5.50 = 20.00)
- A rejection test (discount > subtotal raises ValueError)

Final converge.

## The numbers

| | |
|---|---|
| Turns | 15 (the boundary's max — the agent used the full budget) |
| Cost | $0.124 (Haiku) |
| Tokens | 103,696 |
| Duration | ~51 seconds |
| Tool calls | 19 (6 bash, 9 read_file, 4 write_file) |
| Verifier evaluations | **23** |
| Verifier passes | 20 |
| Verifier fails | 3 (clustered on turns 4, 5, 6) |
| Recovery | Turn 7 |

## What this proves about AVP

Every piece of the protocol earned its place in this run.

**`Commission.allowed_tools`** restricted the agent to `bash` / `read_file` / `write_file`. The model couldn't reach for any other tool the SDK might have exposed.

**`Commission.boundary`** capped the run at 15 turns. If the agent had stayed in the failure loop indefinitely, the boundary would have terminated it deterministically.

**`Commission.verifiers` × `trigger`** put deterministic checks at the right lifecycle points:
- `on_tool:write_file` — instant write-time gates (purity + naming)
- `after_each_turn` — heavier gate (full pytest)

**`Commission.verifiers` × `on_failure: inject_correction`** turned a failing rule into a teaching moment. The supervisor's text became the agent's next user-role message and changed the agent's strategy from "weaken the invariant" to "restructure the feature."

**The trajectory** is a complete audit log. A reviewer reading 23 verifier_evaluated events plus the model_turn_started/ended sequence can reconstruct the entire arc — wrong move, correction, friction, recovery, DDD-correct convergence — without seeing a single LLM-generated word of explanation.

**The three trajectory classes (§10)** carry their weight:

- **What the agent did**: 19 tool calls, 4 write events, all logged.
- **What the rules said**: 23 verifier evaluations with passed/failed plus the failing test's stdout.
- **What the run cost**: $0.124, 103K tokens, 51s — running totals on every cost_recorded event.

A non-technical reviewer can answer "did the agent end up with code that respects DDD invariants?" by looking at one number: `verifier_failed: 3` clustered early, then `passed: true` for the rest of the run. They never have to read code.

## The general pattern

This run is one instance of a reusable pattern:

1. **Encode policy as deterministic verifiers.** Map every architectural / safety / domain concern to one shell command per verifier.
2. **Pick triggers that match cadence.** Cheap checks (file naming, grep) on every write. Expensive checks (test suites) once per turn.
3. **Pick `on_failure` to match recoverability.** Architectural contracts halt; invariant violations inject corrections; advisory checks continue.
4. **Encode the principle, not just the rule, in the correction.** The supervisor's correction here didn't just say "tests failed." It said "don't loosen the invariant." That's the part the agent reasoned about.
5. **Trust the boundary.** With these checks active, you can let the agent run until convergence. If it can't recover, the boundary stops it; if it can, you get a DDD-correct result for ~$0.12.

This generalizes. Replace `domain/` with your bounded context. Replace
`tests/invariants/` with your business-rule suite. Replace the
`correction_message` with the principle from your domain expert. The pattern
fires for any policy you can compile to a shell command.

## What didn't happen

Worth noting what AVP did NOT have to do:

- **No mid-run reach-in.** The supervisor sent a Commission and observed. The "intervention" in turn 4 was the agent-side verifier firing a declared rule, not the supervisor reaching in.
- **No prompt engineering tricks.** The DDD principle lives in `correction_message` — a structured field, not a hidden system prompt.
- **No custom event types.** Every event in the trajectory is a v0.1 standard event type.
- **No bespoke agent work.** The same `avp-anthropic` agent that handles examples 01 and 02 handled this. The supervisor profile changed; the agent did not.

That's the test of a protocol: the more you can do with the standard primitives, the better the protocol. AVP v0.1 has 17 event types and 4 verifier triggers. They were enough.

# 04_ddd_domain — toy DDD codebase for the DDD-strict supervisor demo

A hand-written, deliberately small Domain-Driven Design example. Used as the
workspace for `examples/04_ddd_supervisor.py`. Read this directory and the
profile in `simple_supervisor.profiles.DDD_STRICT` together — they show how
a supervisor compiles bounded-context concerns into AEP verifiers.

## Layout

```
domain/
  order/                         # Order bounded context
    order.py                     #   Aggregate root: Order
    order_line.py                #   Value object: OrderLine
    order_status.py              #   Value object: OrderStatus enum
  customer/                      # Customer bounded context
    customer.py                  #   Aggregate root: Customer
    email_address.py             #   Value object: EmailAddress
tests/
  invariants/                    # Deterministic Boolean rules — the verifier surface
    test_order_invariants.py     #   total == sum(lines), state transitions, ...
    test_customer_invariants.py  #   email validation, value-object equality, ...
```

## DDD properties this codebase demonstrates

- **Aggregate roots own their invariants.** `Order.submit()`, `Order.ship()`,
  `Order.cancel()` enforce state-transition rules on the Order itself — there
  is no `OrderManager` orchestrating them externally.
- **Value objects are immutable.** `OrderLine` and `EmailAddress` are frozen
  dataclasses; equality is structural.
- **Cross-context references are by ID.** `Order.customer_id` is a `str`,
  not a reference to the `Customer` entity. Bounded contexts don't reach
  into each other's models.
- **Domain layer is pure.** No infrastructure imports — no databases, no HTTP
  clients, no queues. The `domain-layer-purity` verifier in `DDD_STRICT`
  enforces this.
- **Ubiquitous language.** Files are named after business concepts (`order.py`,
  `customer.py`), not patterns (`order_manager.py`). The
  `no-anemic-suffixes-in-domain` verifier enforces this.

## Running the invariants directly

From the repo root:

```bash
uv run pytest python/supervisors/simple-supervisor-example/examples/04_ddd_domain/tests/invariants/ -q
```

Or from inside this directory (the verifier itself uses this exact form,
because it runs in the runner's CWD which is staged from a copy of this dir):

```bash
cd python/supervisors/simple-supervisor-example/examples/04_ddd_domain
python -m pytest tests/invariants/ -q
```

20+ tests on the clean baseline. The `aggregate-invariants` verifier in
`DDD_STRICT` runs this exact command after every model turn during an
agent session.

## Extending it

Add new aggregates under `domain/<context>/`. Add their invariants to
`tests/invariants/test_<context>_invariants.py`. The supervisor profile
doesn't need updates — it runs whatever's under `tests/invariants/`.

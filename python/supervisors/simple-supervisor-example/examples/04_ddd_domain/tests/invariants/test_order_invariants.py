"""Aggregate invariants for the Order context.

These tests pin the rules that MUST hold on any Order aggregate state. The
DDD_STRICT supervisor profile runs them after every model turn (via
`pytest tests/invariants/`). If an agent edit breaks any invariant, the
verifier emits passed=false with on_failure=halt — the run terminates.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from domain.order import Order, OrderLine, OrderStatus


def _line(sku: str = "A", qty: int = 1, price: str = "1.00") -> OrderLine:
    return OrderLine(sku=sku, quantity=qty, unit_price=Decimal(price))


# ── Order.total invariant ─────────────────────────────────────────────────────


def test_order_total_equals_sum_of_line_subtotals() -> None:
    """The aggregate's running total is always sum(line.subtotal)."""
    order = Order(
        id="o-1",
        customer_id="c-1",
        lines=[
            OrderLine(sku="A", quantity=2, unit_price=Decimal("10.00")),
            OrderLine(sku="B", quantity=1, unit_price=Decimal("5.50")),
        ],
    )
    assert order.total == Decimal("25.50")


def test_empty_order_total_is_zero() -> None:
    order = Order(id="o", customer_id="c")
    assert order.total == Decimal("0")


def test_adding_a_line_updates_total() -> None:
    order = Order(id="o", customer_id="c")
    assert order.total == Decimal("0")
    order.add_line(_line(qty=3, price="2.00"))
    assert order.total == Decimal("6.00")


# ── State transition invariants ───────────────────────────────────────────────


def test_cannot_submit_empty_order() -> None:
    order = Order(id="o", customer_id="c")
    with pytest.raises(ValueError, match="empty"):
        order.submit()


def test_submit_changes_status_to_submitted() -> None:
    order = Order(id="o", customer_id="c", lines=[_line()])
    order.submit()
    assert order.status == OrderStatus.SUBMITTED


def test_cannot_submit_twice() -> None:
    order = Order(id="o", customer_id="c", lines=[_line()])
    order.submit()
    with pytest.raises(ValueError, match="cannot submit"):
        order.submit()


def test_only_submitted_orders_can_ship() -> None:
    order = Order(id="o", customer_id="c", lines=[_line()])
    with pytest.raises(ValueError, match="only SUBMITTED"):
        order.ship()


def test_submitted_order_can_ship() -> None:
    order = Order(id="o", customer_id="c", lines=[_line()])
    order.submit()
    order.ship()
    assert order.status == OrderStatus.SHIPPED


def test_cannot_add_line_after_submit() -> None:
    order = Order(id="o", customer_id="c", lines=[_line()])
    order.submit()
    with pytest.raises(ValueError, match="cannot add line"):
        order.add_line(_line())


def test_cancelled_orders_are_terminal() -> None:
    order = Order(id="o", customer_id="c", lines=[_line()])
    order.cancel()
    with pytest.raises(ValueError, match="cannot cancel"):
        order.cancel()


def test_shipped_orders_cannot_be_cancelled() -> None:
    order = Order(id="o", customer_id="c", lines=[_line()])
    order.submit()
    order.ship()
    with pytest.raises(ValueError, match="cannot cancel"):
        order.cancel()


# ── OrderLine value-object invariants ─────────────────────────────────────────


def test_order_line_quantity_must_be_positive() -> None:
    with pytest.raises(ValueError, match="quantity"):
        OrderLine(sku="A", quantity=0, unit_price=Decimal("1.00"))


def test_order_line_unit_price_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="unit_price"):
        OrderLine(sku="A", quantity=1, unit_price=Decimal("-0.01"))


def test_order_line_is_immutable() -> None:
    import dataclasses

    line = _line()
    with pytest.raises(dataclasses.FrozenInstanceError):
        line.quantity = 99  # type: ignore[misc]

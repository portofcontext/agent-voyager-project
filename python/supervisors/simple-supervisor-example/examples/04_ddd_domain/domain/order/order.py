"""Order — aggregate root for the Order bounded context.

Aggregate invariants:
  - Order.total == sum(line.subtotal for line in lines)
  - A SUBMITTED order has at least one line
  - A SHIPPED order can only come from SUBMITTED
  - A CANCELLED order is terminal — no further transitions

Behavior that mutates an Order MUST live on this class. Don't extract
"OrderManager" / "OrderService" — that fragments the aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from domain.order.order_line import OrderLine
from domain.order.order_status import OrderStatus


@dataclass
class Order:
    id: str
    customer_id: str  # cross-context reference is by ID, never by entity
    lines: list[OrderLine] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING

    @property
    def total(self) -> Decimal:
        """The aggregate's running total. Always equal to sum of line subtotals."""
        return sum((line.subtotal for line in self.lines), Decimal("0"))

    def add_line(self, line: OrderLine) -> None:
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"cannot add line to order in status {self.status.value}")
        self.lines.append(line)

    def submit(self) -> None:
        if not self.lines:
            raise ValueError("cannot submit an empty order")
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"cannot submit order in status {self.status.value}")
        self.status = OrderStatus.SUBMITTED

    def ship(self) -> None:
        if self.status != OrderStatus.SUBMITTED:
            raise ValueError(f"only SUBMITTED orders can ship; this one is {self.status.value}")
        self.status = OrderStatus.SHIPPED

    def cancel(self) -> None:
        if self.status in (OrderStatus.SHIPPED, OrderStatus.CANCELLED):
            raise ValueError(f"cannot cancel order in status {self.status.value}")
        self.status = OrderStatus.CANCELLED

"""OrderLine — value object representing one line item on an Order.

Value objects are immutable (frozen dataclass) and equality is structural.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price: Decimal

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"OrderLine.quantity must be positive, got {self.quantity}")
        if self.unit_price < 0:
            raise ValueError(f"OrderLine.unit_price must be non-negative, got {self.unit_price}")

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity

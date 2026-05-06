"""OrderStatus — the lifecycle of an Order in the ubiquitous language."""

from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"

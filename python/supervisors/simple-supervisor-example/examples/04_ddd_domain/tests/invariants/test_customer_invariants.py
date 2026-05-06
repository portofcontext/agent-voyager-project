"""Aggregate invariants for the Customer context."""

from __future__ import annotations

import pytest
from domain.customer import Customer, EmailAddress


def test_email_address_validates_at_construction() -> None:
    with pytest.raises(ValueError, match="invalid email"):
        EmailAddress("not-an-email")


def test_email_address_accepts_well_formed_address() -> None:
    e = EmailAddress("alice@example.com")
    assert e.value == "alice@example.com"


def test_email_address_is_immutable() -> None:
    import dataclasses

    e = EmailAddress("a@b.co")
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.value = "x@y.co"  # type: ignore[misc]


def test_email_address_equality_is_structural() -> None:
    a = EmailAddress("alice@example.com")
    b = EmailAddress("alice@example.com")
    assert a == b


def test_customer_change_email_updates_address() -> None:
    c = Customer(id="c-1", name="Alice", email=EmailAddress("alice@example.com"))
    c.change_email(EmailAddress("alice@new.example.com"))
    assert c.email == EmailAddress("alice@new.example.com")


def test_customer_change_email_to_same_is_noop() -> None:
    e = EmailAddress("alice@example.com")
    c = Customer(id="c-1", name="Alice", email=e)
    c.change_email(e)
    assert c.email is e

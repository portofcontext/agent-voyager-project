"""Customer — aggregate root for the Customer bounded context."""

from __future__ import annotations

from dataclasses import dataclass

from domain.customer.email_address import EmailAddress


@dataclass
class Customer:
    id: str
    name: str
    email: EmailAddress

    def change_email(self, new_email: EmailAddress) -> None:
        """Updating an email is a meaningful business event in the customer
        context. Goes on the aggregate, not in a `CustomerEmailManager`."""
        if new_email == self.email:
            return
        self.email = new_email

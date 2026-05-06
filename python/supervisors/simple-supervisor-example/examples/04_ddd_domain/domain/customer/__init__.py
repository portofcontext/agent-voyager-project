"""Customer bounded context."""

from domain.customer.customer import Customer
from domain.customer.email_address import EmailAddress

__all__ = ["Customer", "EmailAddress"]

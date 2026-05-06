"""Domain layer.

Pure business logic. MUST NOT import infrastructure (databases, HTTP, queues).
Two bounded contexts ship here: order/ and customer/. Each context owns its
own aggregate roots and value objects; cross-context references go through
explicit ID fields, not entity references.
"""

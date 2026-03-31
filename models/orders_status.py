from enum import Enum


class OrderStatus(str, Enum):
    # Order created, waiting for worker to pick it up
    PENDING = "PENDING"

    # Worker is actively attempting payment
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"

    # Payment attempt failed (may still retry)
    PAYMENT_FAILED = "PAYMENT_FAILED"

    # Worker is actively checking inventory
    INVENTORY_PROCESSING = "INVENTORY_PROCESSING"

    # Inventory check failed (may still retry)
    INVENTORY_CHECK_FAILED = "INVENTORY_CHECK_FAILED"

    # Legacy — kept for backwards compat
    INVENTORY_CHECK = "INVENTORY_CHECK"

    # FIX (BUG 1): Added missing INVENTORY_RESERVED state.
    # order_processor.py sets this after inventory is successfully reserved,
    # but this value was never defined in the enum — causing an AttributeError
    # crash on every single successful inventory check.
    INVENTORY_RESERVED = "INVENTORY_RESERVED"

    # All steps passed
    COMPLETED = "COMPLETED"

    # Exhausted all retries, order could not be fulfilled
    FAILED = "FAILED"

    # Explicitly cancelled by user
    CANCELLED = "CANCELLED"
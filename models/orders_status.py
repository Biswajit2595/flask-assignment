from enum import Enum


class OrderStatus(str, Enum):
    """ Possible lifecycle states of an order."""
    # Order created and waiting to be processed by a worker
    PENDING = "PENDING"

    # Worker is attempting to process payment
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"

    # Payment attempt failed but may still be retried
    PAYMENT_FAILED = "PAYMENT_FAILED"

    # Worker is checking inventory availability
    INVENTORY_PROCESSING = "INVENTORY_PROCESSING"

    # Inventory check failed but may still be retried
    INVENTORY_CHECK_FAILED = "INVENTORY_CHECK_FAILED"

    # Legacy state kept for backward compatibility
    INVENTORY_CHECK = "INVENTORY_CHECK"

    # Inventory successfully reserved for the order
    INVENTORY_RESERVED = "INVENTORY_RESERVED"

    # Order completed successfully
    COMPLETED = "COMPLETED"

    # Order failed after exhausting retries
    FAILED = "FAILED"

    # Order cancelled by the user
    CANCELLED = "CANCELLED"
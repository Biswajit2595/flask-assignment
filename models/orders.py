from datetime import datetime, timezone
from database import db
import uuid
from models.orders_status import OrderStatus


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key = db.Column(db.String(255), unique=True, nullable=True)
    items = db.Column(db.JSON, nullable=False)
    status = db.Column(
        db.String,
        default=OrderStatus.PENDING.value,
        nullable=False
    )

    payment_retry_count = db.Column(db.Integer, default=0)
    inventory_retry_count = db.Column(db.Integer, default=0)
    payment_reference = db.Column(db.String, nullable=True)
    recovery_attempts = db.Column(db.Integer, default=0)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "items": self.items,
            "status": self.status,
            "payment_retry_count": self.payment_retry_count,
            "inventory_retry_count": self.inventory_retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
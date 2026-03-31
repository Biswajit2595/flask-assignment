import random
import time

from sqlalchemy import update

from database import db
from models.inventory import Inventory


def check_inventory(order):
    """
    Reserve inventory atomically using a conditional UPDATE.

    WHY NOT SELECT + UPDATE:
    That approach has a race condition:
    1. SELECT quantity
    2. Check quantity >= needed
    3. UPDATE quantity

    Two threads could read the same quantity and both subtract,
    causing overselling.

    Using a single atomic UPDATE removes this gap:

    UPDATE inventory
    SET quantity = quantity - :needed
    WHERE item_name = :name AND quantity >= :needed

    The database performs the check and update in one step.
    If two threads run concurrently, one succeeds (rowcount=1)
    and the other fails (rowcount=0).

    This works reliably across SQLite, PostgreSQL, and MySQL.

    DEADLOCK PREVENTION:
    Items are processed in sorted order so multiple orders
    lock rows in the same sequence.
    """

    # Simulate external service delay
    time.sleep(1)

    # simulate 20% inventory service failure
    if random.random() < 0.2:
        return {
            "success": False,
            "error": "Inventory service failure"
        }

    # Sort items alphabetically — consistent order prevents deadlocks
    items = sorted(order.items, key=lambda x: x["name"])

    try:
        for item in items:
            # Atomic update prevents race conditions and overselling
            result = db.session.execute(
                update(Inventory)
                .where(
                    Inventory.item_name == item["name"],
                    Inventory.quantity >= item["quantity"]
                )
                .values(quantity=Inventory.quantity - item["quantity"])
                .execution_options(synchronize_session="fetch")
            )

            if result.rowcount == 0:
                # rowcount == 0 → item missing or insufficient stock
                # rollback previous deductions for this order
                db.session.rollback()

                inventory = db.session.query(Inventory).filter_by(
                    item_name=item["name"]
                ).first()

                if not inventory:
                    return {
                        "success": False,
                        "error": f"Item '{item['name']}' not found in inventory"
                    }

                return {
                    "success": False,
                    "error": (
                        f"Insufficient stock for '{item['name']}': "
                        f"requested {item['quantity']}, "
                        f"available {inventory.quantity}"
                    )
                }

        # commit all reservations
        db.session.commit()
        return {"success": True}

    except Exception as e:
        db.session.rollback()
        return {
            "success": False,
            "error": f"Inventory reservation failed: {str(e)}"
        }


def release_inventory(order):
    """
    Release reserved inventory.

    Used when:
    1. Payment permanently fails
    2. Order is cancelled
    """

    items = sorted(order.items, key=lambda x: x["name"])

    try:
        for item in items:
            db.session.execute(
                update(Inventory)
                .where(Inventory.item_name == item["name"])
                .values(quantity=Inventory.quantity + item["quantity"])
                .execution_options(synchronize_session="fetch")
            )

        db.session.commit()
        return {"success": True}

    except Exception as e:
        db.session.rollback()
        return {
            "success": False,
            "error": f"Inventory release failed: {str(e)}"
        }
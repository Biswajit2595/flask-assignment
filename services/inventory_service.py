
# import random
# import time

# from database import db
# from models.inventory import Inventory


# def check_inventory(order):
#     """
#     Reserve inventory for an order.

#     Uses row-level locking to avoid race conditions when
#     multiple workers try to reserve the same item.
#     """

#     # simulate external service delay
#     time.sleep(1)

#     # 20% failure chance (assignment requirement)
#     if random.random() < 0.2:
#         return {
#             "success": False,
#             "error": "Inventory service failure"
#         }

#     try:

#         # sort items to prevent deadlocks
#         items = sorted(order.items, key=lambda x: x["name"])

#         for item in items:

#             inventory = (
#                 db.session.query(Inventory)
#                 .filter_by(item_name=item["name"])
#                 .with_for_update()
#                 .first()
#             )

#             if not inventory:
#                 return {
#                     "success": False,
#                     "error": f"{item['name']} not found"
#                 }

#             if inventory.quantity < item["quantity"]:
#                 return {
#                     "success": False,
#                     "error": f"Not enough {item['name']}"
#                 }

#             # reserve inventory
#             inventory.quantity -= item["quantity"]

#         db.session.commit()

#         return {
#             "success": True
#         }

#     except Exception as e:

#         db.session.rollback()

#         return {
#             "success": False,
#             "error": str(e)
#         }


# def release_inventory(order):
#     """
#     Release previously reserved inventory.
#     Used when payment permanently fails after inventory reservation.
#     """

#     try:

#         items = sorted(order.items, key=lambda x: x["name"])

#         for item in items:

#             inventory = (
#                 db.session.query(Inventory)
#                 .filter_by(item_name=item["name"])
#                 .with_for_update()
#                 .first()
#             )

#             if inventory:
#                 inventory.quantity += item["quantity"]

#         db.session.commit()

#         return {
#             "success": True
#         }

#     except Exception as e:

#         db.session.rollback()

#         return {
#             "success": False,
#             "error": str(e)
#         }


import random
import time

from sqlalchemy import update

from database import db
from models.inventory import Inventory


def check_inventory(order):
    """
    Reserve inventory for all items in an order atomically.

    WHY ATOMIC UPDATE INSTEAD OF with_for_update():
    ------------------------------------------------
    The old approach was:
        1. SELECT row        (read quantity)
        2. Check in Python   (quantity >= needed?)
        3. UPDATE row        (write new quantity)

    Steps 1→3 are three separate operations. Between step 1 and step 3,
    another thread can read the same quantity and also decide "enough stock
    exists." Both then subtract. Result: oversold inventory (e.g. -3 burgers).

    with_for_update() fixes this by locking the row at step 1, blocking all
    other readers until step 3 commits. But on SQLite, FOR UPDATE is silently
    ignored — the race still exists.

    Atomic UPDATE collapses all three steps into one SQL statement:

        UPDATE inventory
        SET quantity = quantity - :needed
        WHERE item_name = :name
          AND quantity >= :needed

    The DB engine executes the check and the write in a single operation.
    No gap. Two concurrent threads firing this same statement are serialized
    internally by the DB — one gets rowcount=1 (success), the other rowcount=0
    (out of stock). Works on SQLite, PostgreSQL, MySQL — everywhere.

    DEADLOCK PREVENTION:
    --------------------
    Items are sorted alphabetically before processing. If two orders both want
    [burger, fries], they always try burger first, then fries — same order.
    This prevents Order A locking burger/waiting for fries while Order B locks
    fries/waiting for burger. Consistent lock ordering eliminates circular waits.
    """

    # Simulate external service delay (assignment requirement)
    time.sleep(1)

    # 20% random failure to simulate flaky inventory service (assignment requirement)
    if random.random() < 0.2:
        return {
            "success": False,
            "error": "Inventory service failure"
        }

    # Sort items alphabetically — consistent order prevents deadlocks
    items = sorted(order.items, key=lambda x: x["name"])

    try:
        for item in items:

            # Atomic conditional UPDATE:
            # Subtracts quantity ONLY IF sufficient stock exists.
            # The WHERE clause is the guard — no separate SELECT needed.
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
                # rowcount == 0 means either:
                #   (a) item doesn't exist in inventory table, OR
                #   (b) item exists but quantity < needed (out of stock)
                #
                # Roll back any deductions already committed for earlier items
                # in this same order (e.g. fries were reserved, burger failed).
                db.session.rollback()

                # Distinguish "not found" vs "insufficient" for clear error messages
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

        # All items reserved — commit all deductions atomically
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
    Return previously reserved inventory back to stock.

    Called in two scenarios:
      1. Payment permanently fails after inventory was already reserved —
         must undo the reservation so stock isn't locked forever.
      2. Order is cancelled after inventory was reserved (Phase 8).

    No conditional check needed here — we're always adding back, never
    subtracting, so no oversell risk. Sorted order matches check_inventory
    for consistency.
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
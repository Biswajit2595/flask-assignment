from database import db
from models.orders import Order
from models.orders_status import OrderStatus

from services.payment_service import process_payment
from services.inventory_service import check_inventory, release_inventory

from constants.order_constants import MAX_PAYMENT_RETRIES, MAX_INVENTORY_RETRIES

from workers.queue import enqueue_order 

from utils.logger import get_logger

logger = get_logger("order_processor")


def process_order(order_id):

    logger.info(f"[ORDER_START] Processing started for order {order_id}")

    order = (
        db.session.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if not order:
        logger.warning(f"[ORDER_NOT_FOUND] Order {order_id} does not exist")
        return

    logger.info(
        f"[ORDER_STATE] Order {order.id} current status: {order.status}"
    )

    # PHASE 8 — CANCELLED GUARD
    if order.status == OrderStatus.CANCELLED.value:
        logger.info(
            f"[ORDER_CANCELLED] Order {order_id} already cancelled. Skipping processing."
        )
        db.session.commit()
        return

    # TERMINAL STATE CHECK
    if order.status == OrderStatus.COMPLETED.value:
        logger.info(f"[ORDER_SKIP] Order {order.id} already completed")
        db.session.commit()
        return

    # INVENTORY STEP
    if order.status in [
        OrderStatus.PENDING.value,
        OrderStatus.INVENTORY_PROCESSING.value
    ]:

        logger.info(f"[INVENTORY_START] Checking inventory for order {order.id}")

        order.status = OrderStatus.INVENTORY_PROCESSING.value
        logger.info(f"[STATE_CHANGE] Order {order.id} → INVENTORY_PROCESSING")
        db.session.commit()

        inventory_result = check_inventory(order)

        if not inventory_result["success"]:

            order.inventory_retry_count += 1

            logger.warning(
                f"[INVENTORY_FAILED] Order {order.id} | "
                f"reason={inventory_result.get('error')} | "
                f"retry={order.inventory_retry_count}"
            )

            if order.inventory_retry_count >= MAX_INVENTORY_RETRIES:

                logger.error(
                    f"[INVENTORY_PERMANENT_FAILURE] Order {order.id} exceeded max retries"
                )

                order.status = OrderStatus.FAILED.value
                logger.info(f"[STATE_CHANGE] Order {order.id} → FAILED")

                db.session.commit()
                logger.info(f"[ORDER_END] Processing cycle ended for order {order.id}")
                return

            else:

                # INVENTORY RETRY
                order.status = OrderStatus.PENDING.value

                logger.info(
                    f"[INVENTORY_RETRY_SCHEDULED] Order {order.id} will retry inventory"
                )
                logger.info(f"[STATE_CHANGE] Order {order.id} → PENDING")

                db.session.commit()

                enqueue_order(order.id)
                logger.info(f"[ORDER_REQUEUED] Order {order.id} added back to queue")

                logger.info(f"[ORDER_END] Processing cycle ended for order {order.id}")
                return

        logger.info(f"[INVENTORY_SUCCESS] Inventory reserved for order {order.id}")

        order.status = OrderStatus.INVENTORY_RESERVED.value
        logger.info(f"[STATE_CHANGE] Order {order.id} → INVENTORY_RESERVED")

        db.session.commit()

        # Refresh in case cancellation happened meanwhile
        db.session.refresh(order)

        if order.status == OrderStatus.CANCELLED.value:

            logger.info(
                f"[ORDER_CANCELLED] Order {order.id} cancelled after inventory reservation"
            )

            release_inventory(order)

            logger.info(
                f"[INVENTORY_RELEASED] Inventory returned for order {order.id}"
            )

            db.session.commit()
            return

    else:
        logger.info(
            f"[INVENTORY_SKIP] Inventory already reserved for order {order.id}"
        )

    # PAYMENT STEP
    if not order.payment_reference:

        logger.info(f"[PAYMENT_START] Processing payment for order {order.id}")

        order.status = OrderStatus.PAYMENT_PROCESSING.value
        logger.info(f"[STATE_CHANGE] Order {order.id} → PAYMENT_PROCESSING")

        db.session.commit()

        payment_result = process_payment(order.id)

        if not payment_result["success"]:

            order.payment_retry_count += 1

            logger.warning(
                f"[PAYMENT_FAILED] Order {order.id} | "
                f"reason={payment_result.get('error')} | "
                f"retry={order.payment_retry_count}"
            )

            if order.payment_retry_count >= MAX_PAYMENT_RETRIES:

                logger.error(
                    f"[PAYMENT_PERMANENT_FAILURE] Order {order.id} exceeded max retries"
                )

                # Compensation
                release_inventory(order)

                logger.info(
                    f"[INVENTORY_RELEASED] Inventory returned for order {order.id}"
                )

                order.status = OrderStatus.FAILED.value
                logger.info(f"[STATE_CHANGE] Order {order.id} → FAILED")

                db.session.commit()

                logger.info(f"[ORDER_END] Processing cycle ended for order {order.id}")
                return

            else:

                # PAYMENT RETRY
                order.status = OrderStatus.INVENTORY_RESERVED.value

                logger.info(
                    f"[PAYMENT_RETRY_SCHEDULED] Order {order.id} will retry payment"
                )

                logger.info(
                    f"[STATE_CHANGE] Order {order.id} → INVENTORY_RESERVED"
                )

                db.session.commit()

                enqueue_order(order.id)

                logger.info(
                    f"[ORDER_REQUEUED] Order {order.id} added back to queue for payment retry"
                )

                logger.info(f"[ORDER_END] Processing cycle ended for order {order.id}")
                return

        order.payment_reference = payment_result["payment_reference"]

        logger.info(
            f"[PAYMENT_SUCCESS] Order {order.id} | ref={order.payment_reference}"
        )

        db.session.commit()

    else:
        logger.info(
            f"[PAYMENT_SKIP] Payment already completed for order {order.id}"
        )

    # ORDER COMPLETED
    order.status = OrderStatus.COMPLETED.value

    logger.info(f"[STATE_CHANGE] Order {order.id} → COMPLETED")

    db.session.commit()

    logger.info(f"[ORDER_SUCCESS] Order {order.id} completed successfully")
    logger.info(f"[ORDER_END] Processing cycle finished for order {order.id}")
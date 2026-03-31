import time
import threading
from datetime import datetime, timedelta

from database import db
from models.orders import Order
from models.orders_status import OrderStatus
from workers.queue import enqueue_order
from utils.logger import get_logger
from constants.order_constants import STUCK_ORDER_THRESHOLD_SECONDS,MAX_RECOVERY_ATTEMPTS

logger = get_logger("order_recovery")



def recovery_loop(app):
    """
    Periodically scans the database for orders that appear stuck and
    requeues them for processing.

    An order is considered stuck if:
    - It is not in a terminal state (COMPLETED, FAILED, CANCELLED)
    - It has not been updated recently

    If recovery attempts exceed the allowed limit, the order is marked
    as FAILED to prevent infinite retry loops.
    """

    with app.app_context():
        logger.info("[RECOVERY_WORKER_STARTED]")

        while True:

            try:

                threshold = datetime.utcnow() - timedelta(
                    seconds=STUCK_ORDER_THRESHOLD_SECONDS
                )

                stuck_orders = (
                    db.session.query(Order)
                    .filter(
                        Order.status.notin_([
                            OrderStatus.COMPLETED.value,
                            OrderStatus.FAILED.value,
                            OrderStatus.CANCELLED.value
                        ]),
                        Order.updated_at < threshold
                    )
                    .all()
                )

                for order in stuck_orders:

                    order.recovery_attempts += 1

                    if order.recovery_attempts > MAX_RECOVERY_ATTEMPTS:

                        order.status = OrderStatus.FAILED.value

                        logger.warning(
                            f"[RECOVERY_ABORTED] Order {order.id} exceeded "
                            f"max recovery attempts ({MAX_RECOVERY_ATTEMPTS}). "
                            f"Marking as FAILED."
                        )

                        continue

                    logger.info(
                        f"[RECOVERY_REQUEUE] Order {order.id} "
                        f"status={order.status} "
                        f"attempt={order.recovery_attempts}"
                    )

                    enqueue_order(order.id)

                db.session.commit()

            except Exception as e:
                logger.error(f"[RECOVERY_WORKER_ERROR] {str(e)}")
                db.session.rollback()

            # Run periodically
            time.sleep(30)


def start_recovery_worker(app):
    """
    Starts the background recovery worker thread.
    """

    thread = threading.Thread(
        target=recovery_loop,
        args=(app,),
        daemon=True
    )

    thread.start()

    logger.info("[RECOVERY_WORKER_THREAD_STARTED]")
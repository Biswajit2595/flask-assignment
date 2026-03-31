import time
import threading

from database import db
from models.orders import Order
from models.orders_status import OrderStatus
from workers.queue import enqueue_order
from utils.logger import get_logger

logger = get_logger("order_recovery")


def recovery_loop(app):
    """
    Periodically scans the database for orders that are not in a terminal
    state and requeues them. This helps recover orders that got stuck due
    to worker crashes or missed retries.
    """

    with app.app_context():

        logger.info("[RECOVERY_WORKER_STARTED] Order recovery worker started")

        while True:

            try:

                # Find orders that are not completed/failed/cancelled
                stuck_orders = (
                    db.session.query(Order)
                    .filter(
                        Order.status.notin_([
                            OrderStatus.COMPLETED.value,
                            OrderStatus.FAILED.value,
                            OrderStatus.CANCELLED.value
                        ])
                    )
                    .all()
                )

                for order in stuck_orders:

                    logger.info(
                        f"[RECOVERY_REQUEUE] Order {order.id} status={order.status}"
                    )

                    enqueue_order(order.id)

                db.session.commit()

            except Exception as e:

                logger.error(f"[RECOVERY_WORKER_ERROR] {str(e)}")
                db.session.rollback()

            # Run every 30 seconds
            time.sleep(30)


def start_recovery_worker(app):
    """
    Starts the recovery worker thread.
    """

    thread = threading.Thread(
        target=recovery_loop,
        args=(app,),
        daemon=True
    )

    thread.start()

    logger.info("[RECOVERY_WORKER_THREAD_STARTED]")
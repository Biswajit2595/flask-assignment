
import threading
import time

from workers.queue import dequeue_order, enqueue_order
from services.order_processor import process_order
from models.orders import Order
from models.orders_status import OrderStatus
from utils.logger import get_logger

logger = get_logger("order_worker")

_shutdown_flag = threading.Event()


def worker_loop(app):

    with app.app_context():

        while not _shutdown_flag.is_set():

            # dequeue_order now returns None on timeout (every 1s),
            # which lets the while-condition re-evaluate for shutdown.
            order_id = dequeue_order(timeout=1)

            if not order_id:
                # Queue was empty — loop back and check shutdown flag
                continue

            logger.info(f"[WORKER_DEQUEUED] Picked up order {order_id}")

            try:

                order = Order.query.get(order_id)

                if not order:
                    logger.warning(f"[WORKER_SKIP] Order {order_id} not found in DB")
                    continue

                # Skip if already in a terminal state — prevents duplicate
                # worker execution if the same order_id was enqueued twice
                if order.status in (
                    OrderStatus.COMPLETED.value,
                    OrderStatus.FAILED.value,
                    OrderStatus.CANCELLED.value,
                ):
                    logger.info(
                        f"[WORKER_SKIP] Order {order_id} already in terminal "
                        f"state: {order.status}"
                    )
                    continue

                process_order(order_id)

                # Fetch updated order to check if retry is needed
                order = Order.query.get(order_id)

                if order and order.status == OrderStatus.PENDING.value:
                    logger.info(
                        f"[WORKER_RETRY] Order {order_id} back to PENDING — "
                        f"re-enqueueing with backoff"
                    )
                    time.sleep(2)
                    enqueue_order(order_id)

            except Exception as e:
                logger.error(f"[WORKER_ERROR] Exception processing order {order_id}: {e}")


def start_worker(app):
    worker = threading.Thread(
        target=worker_loop,
        args=(app,),
        daemon=True,
        name="order-worker"
    )
    worker.start()
    logger.info("[WORKER_STARTED] Background order worker started")
    return worker


def stop_worker():
    """Signal the worker loop to exit cleanly on next iteration."""
    _shutdown_flag.set()
    logger.info("[WORKER_STOPPING] Shutdown signal sent to worker")
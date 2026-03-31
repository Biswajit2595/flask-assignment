
import queue

# Global in-memory queue
order_queue = queue.Queue()


def enqueue_order(order_id):
    order_queue.put(order_id)


def dequeue_order(timeout=1):

    try:
        return order_queue.get(timeout=timeout)
    except queue.Empty:
        return None
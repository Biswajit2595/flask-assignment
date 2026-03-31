# import queue

# # global in-memory queue
# order_queue = queue.Queue()


# def enqueue_order(order_id):
#     order_queue.put(order_id)


# def dequeue_order():
#     return order_queue.get()


import queue

# Global in-memory queue
order_queue = queue.Queue()


def enqueue_order(order_id):
    order_queue.put(order_id)


def dequeue_order(timeout=1):
    """
    FIX (BUG 2): Added timeout parameter to queue.get().

    The original queue.get() had no timeout, which blocked the worker thread
    indefinitely when the queue was empty. This meant:
      - The worker thread could never be shut down gracefully.
      - No shutdown signal could ever be injected.
      - Test teardown would hang.

    With timeout=1, the worker wakes up every second, checks if it should
    stop, and goes back to waiting. Returns None on timeout so the caller
    can handle it cleanly.
    """
    try:
        return order_queue.get(timeout=timeout)
    except queue.Empty:
        return None
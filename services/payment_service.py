import random
import time
import uuid


def process_payment(order_id):

    # simulate network delay
    time.sleep(1)

    # 30% failure chance
    success = random.random() > 0.3

    if not success:
        return {
            "success": False,
            "error": "Payment failed"
        }

    return {
        "success": True,
        "payment_reference": f"PAY-{uuid.uuid4()}"
    }
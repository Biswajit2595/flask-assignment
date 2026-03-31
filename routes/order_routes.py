# from flask import Blueprint, request, jsonify
# from marshmallow import ValidationError
# from models.orders import Order
# from models.orders_status import OrderStatus
# from schema.order_schema import CreateOrderSchema
# from database import db
# from workers.queue import enqueue_order

# order_bp = Blueprint("orders", __name__)

# create_order_schema = CreateOrderSchema()


# def error_response(message, status=400):
#     return jsonify({"error": message}), status


# # -------------------------------
# # Create Order
# # -------------------------------
# # @order_bp.route("/orders", methods=["POST"])
# # def create_order():

# #     data = request.get_json()

# #     if not data:
# #         return error_response("Request body is required")

# #     # marshmallow validates structure, types, and constraints
# #     try:
# #         validated = create_order_schema.load(data)
# #     except ValidationError as err:
# #         return jsonify({"error": err.messages}), 400

# #     order = Order(items=validated["items"])

# #     db.session.add(order)
# #     db.session.commit()
    
# #     # send order to background worker
# #     enqueue_order(order.id)


# #     response = jsonify(order.to_dict())
# #     response.status_code = 201
# #     response.headers["Location"] = f"/orders/{order.id}"

# #     return response

# @order_bp.route("/orders", methods=["POST"])
# def create_order():

#     data = request.get_json()

#     if not data:
#         return error_response("Request body is required")

#     # marshmallow validation
#     try:
#         validated = create_order_schema.load(data)
#     except ValidationError as err:
#         return jsonify({"error": err.messages}), 400

#     # -----------------------------
#     # Read Idempotency Key
#     # -----------------------------
#     idempotency_key = request.headers.get("Idempotency-Key")

#     if not idempotency_key:
#         return error_response("Idempotency-Key header is required")

#     # -----------------------------
#     # Check for duplicate request
#     # -----------------------------
#     existing_order = Order.query.filter_by(
#         idempotency_key=idempotency_key
#     ).first()

#     if existing_order:
#         response = jsonify(existing_order.to_dict())
#         response.status_code = 200
#         response.headers["Location"] = f"/orders/{existing_order.id}"
#         return response

#     # -----------------------------
#     # Create new order
#     # -----------------------------
#     order = Order(
#         items=validated["items"],
#         idempotency_key=idempotency_key
#     )

#     db.session.add(order)
#     db.session.commit()

#     # send to worker
#     enqueue_order(order.id)

#     response = jsonify(order.to_dict())
#     response.status_code = 201
#     response.headers["Location"] = f"/orders/{order.id}"

#     return response

# # -------------------------------
# # Get Order by ID
# # -------------------------------
# @order_bp.route("/orders/<order_id>", methods=["GET"])
# def get_order(order_id):

#     order = db.session.get(Order, order_id)

#     if not order:
#         return error_response("order not found", 404)

#     return jsonify(order.to_dict())


# # -------------------------------
# # List Orders (with filters)
# # -------------------------------
# @order_bp.route("/orders", methods=["GET"])
# def list_orders():

#     status = request.args.get("status")
#     page = request.args.get("page", default=1, type=int)
#     limit = request.args.get("limit", default=10, type=int)

#     # pagination guardrails
#     if page < 1:
#         page = 1

#     if limit < 1 or limit > 100:
#         limit = 10

#     offset = (page - 1) * limit

#     query = Order.query

#     # status filtering
#     if status:
#         # Fix: lookup by name → get the enum object → filter by .value
#         try:
#             status_enum = OrderStatus[status.upper()]
#         except KeyError:
#             return error_response("Invalid status")

#         query = query.filter_by(status=status_enum.value)

#     total = query.count()

#     orders = (
#         query
#         .order_by(Order.created_at.desc())
#         .offset(offset)
#         .limit(limit)
#         .all()
#     )

#     return jsonify({
#         "page": page,
#         "limit": limit,
#         "total": total,
#         "orders": [order.to_dict() for order in orders]
#     })
    
# @order_bp.route("/orders/<order_id>/cancel", methods=["POST"])
# def cancel_order(order_id):

#     order = Order.query.get(order_id)

#     if not order:
#         return jsonify({"error": "Order not found"}), 404

#     # Cannot cancel completed orders
#     if order.status == OrderStatus.COMPLETED:
#         return jsonify({
#             "error": "Completed orders cannot be cancelled"
#         }), 400

#     # If already cancelled
#     if order.status == OrderStatus.CANCELLED:
#         return jsonify({
#             "message": "Order already cancelled"
#         }), 200

#     order.status = OrderStatus.CANCELLED

#     db.session.commit()

#     return jsonify({
#         "message": "Order cancelled successfully",
#         "order_id": order.id
#     })





from flask import Blueprint, request, jsonify
from marshmallow import ValidationError
from sqlalchemy import update

from models.orders import Order
from models.orders_status import OrderStatus
from schema.order_schema import CreateOrderSchema
from database import db
from workers.queue import enqueue_order
from utils.logger import get_logger

logger = get_logger("order_routes")

order_bp = Blueprint("orders", __name__)
create_order_schema = CreateOrderSchema()

# Terminal states — orders in these states cannot be cancelled
TERMINAL_STATES = [
    OrderStatus.COMPLETED.value,
    OrderStatus.FAILED.value,
    OrderStatus.CANCELLED.value,
]


def error_response(message, status=400):
    return jsonify({"error": message}), status


# -------------------------------
# Create Order
# -------------------------------
@order_bp.route("/orders", methods=["POST"])
def create_order():

    data = request.get_json()

    if not data:
        return error_response("Request body is required")

    try:
        validated = create_order_schema.load(data)
    except ValidationError as err:
        return jsonify({"error": err.messages}), 400

    idempotency_key = request.headers.get("Idempotency-Key")

    if not idempotency_key:
        return error_response("Idempotency-Key header is required")

    # Return existing order for duplicate requests — no new order created
    existing_order = Order.query.filter_by(idempotency_key=idempotency_key).first()

    if existing_order:
        logger.info(
            f"[IDEMPOTENCY_HIT] Duplicate request key={idempotency_key} "
            f"→ returning existing order {existing_order.id}"
        )
        response = jsonify(existing_order.to_dict())
        response.status_code = 200
        response.headers["Location"] = f"/orders/{existing_order.id}"
        return response

    order = Order(items=validated["items"], idempotency_key=idempotency_key)
    db.session.add(order)
    db.session.commit()

    logger.info(f"[ORDER_CREATED] Order {order.id} created and enqueued")
    enqueue_order(order.id)

    response = jsonify(order.to_dict())
    response.status_code = 201
    response.headers["Location"] = f"/orders/{order.id}"
    return response


# -------------------------------
# Get Order by ID
# -------------------------------
@order_bp.route("/orders/<order_id>", methods=["GET"])
def get_order(order_id):

    order = db.session.get(Order, order_id)

    if not order:
        return error_response("Order not found", 404)

    return jsonify(order.to_dict())


# -------------------------------
# List Orders (with filters)
# -------------------------------
@order_bp.route("/orders", methods=["GET"])
def list_orders():

    status = request.args.get("status")
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=10, type=int)

    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 10

    offset = (page - 1) * limit
    query = Order.query

    if status:
        try:
            status_enum = OrderStatus[status.upper()]
        except KeyError:
            return error_response("Invalid status")
        query = query.filter_by(status=status_enum.value)

    total = query.count()
    orders = (
        query
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jsonify({
        "page": page,
        "limit": limit,
        "total": total,
        "orders": [order.to_dict() for order in orders]
    })


# -------------------------------
# Cancel Order
# -------------------------------
@order_bp.route("/orders/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    """
    WHY ATOMIC UPDATE INSTEAD OF with_for_update():
    ------------------------------------------------
    The race condition we're protecting against:

        Worker thread:  processing order → about to commit COMPLETED
        Cancel thread:  reads status = PAYMENT_PROCESSING → decides "can cancel"
        Worker thread:  commits COMPLETED
        Cancel thread:  commits CANCELLED  ← overwrites COMPLETED. Wrong.

    with_for_update() fixes this by serializing the two threads at the DB level.
    But on SQLite, FOR UPDATE is silently ignored — the race still exists.

    Atomic conditional UPDATE fixes it properly on any DB:

        UPDATE orders
        SET status = 'CANCELLED'
        WHERE id = :id
          AND status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')

    The WHERE clause is both the guard and the write — one operation, no gap.
    If the worker already committed COMPLETED, the WHERE fails → rowcount=0.
    Cancel correctly rejects itself without ever needing to read first.

    rowcount tells us everything:
      - rowcount == 1  →  cancel succeeded
      - rowcount == 0  →  order was already in a terminal state (or didn't exist)
    """

    try:
        result = db.session.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.status.notin_(TERMINAL_STATES)
            )
            .values(status=OrderStatus.CANCELLED.value)
            .execution_options(synchronize_session="fetch")
        )

        db.session.commit()

        if result.rowcount == 1:
            # Update succeeded — order was in a cancellable state
            logger.info(f"[ORDER_CANCELLED] Order {order_id} successfully cancelled")
            return jsonify({
                "message": "Order cancelled successfully",
                "order_id": order_id
            }), 200

        # rowcount == 0: WHERE condition failed.
        # Re-fetch to return a meaningful response to the caller.
        order = db.session.get(Order, order_id)

        if not order:
            return jsonify({"error": "Order not found"}), 404

        if order.status == OrderStatus.CANCELLED.value:
            # Idempotent — already cancelled, treat as success
            logger.info(f"[CANCEL_IDEMPOTENT] Order {order_id} was already cancelled")
            return jsonify({
                "message": "Order already cancelled",
                "order_id": order_id
            }), 200

        # Order exists but is COMPLETED or FAILED — cannot cancel
        logger.info(
            f"[CANCEL_REJECTED] Order {order_id} in terminal state: {order.status}"
        )
        return jsonify({
            "error": f"Cannot cancel order in '{order.status}' state"
        }), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"[CANCEL_ERROR] Failed to cancel order {order_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500
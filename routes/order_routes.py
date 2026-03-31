
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

# Standardized error response helper
def error_response(message, status=400):
    return jsonify({"error": message}), status


# Create Order
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


# Get Order by ID
@order_bp.route("/orders/<order_id>", methods=["GET"])
def get_order(order_id):

    order = db.session.get(Order, order_id)

    if not order:
        return error_response("Order not found", 404)

    return jsonify(order.to_dict())


# List Orders (with filters)
@order_bp.route("/orders", methods=["GET"])
def list_orders():

    status = request.args.get("status")
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=10, type=int)

    # basic pagination validation
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 10

    offset = (page - 1) * limit
    query = Order.query

    # convert query param to enum value
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


# Cancel Order
@order_bp.route("/orders/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    """
    Atomic cancellation to avoid race conditions.

    Scenario:
    Worker commits COMPLETED while cancel request is executing.
    Without protection, cancel could overwrite COMPLETED.

    SQLite ignores SELECT ... FOR UPDATE, so we use an atomic update:

    UPDATE orders
    SET status = 'CANCELLED'
    WHERE id = :id
    AND status NOT IN ('COMPLETED','FAILED','CANCELLED')

    If the order is already terminal, the WHERE fails and rowcount = 0.
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
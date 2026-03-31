from marshmallow import Schema, fields, validate


class OrderItemSchema(Schema):
    name = fields.String(required=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))


class CreateOrderSchema(Schema):
    items = fields.List(
        fields.Nested(OrderItemSchema),
        required=True,
        validate=validate.Length(min=1)
    )
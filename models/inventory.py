from database import db


class Inventory(db.Model):
    __tablename__ = "inventory"

    item_name = db.Column(db.String, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            "item_name": self.item_name,
            "quantity": self.quantity
        }
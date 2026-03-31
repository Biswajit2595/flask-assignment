from flask import Flask
from database import db
from routes.order_routes import order_bp
from workers.order_worker import start_worker
from workers.recovery_worker import start_recovery_worker
from flask_migrate import Migrate
import os


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///orders.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# Initialize database
db.init_app(app)

# Initialize migrations
migrate = Migrate(app, db)


# Register routes
app.register_blueprint(order_bp)


# Start background worker
if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_worker(app)
    start_recovery_worker(app)


if __name__ == "__main__":
    app.run(debug=True)
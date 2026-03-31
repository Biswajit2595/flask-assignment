# Flask Order Management System

A robust, asynchronous order processing system built with Flask, featuring idempotent operations, background workers, retry logic, and comprehensive error handling.

## Features

- **Asynchronous Order Processing**: Background workers handle order fulfillment without blocking API responses
- **Idempotent Operations**: Duplicate requests are handled gracefully using idempotency keys
- **Retry Logic**: Automatic retries for payment and inventory failures with configurable limits
- **Order Cancellation**: Safe cancellation of orders in non-terminal states
- **Comprehensive Logging**: Detailed logging for debugging and monitoring
- **Database Migrations**: Alembic migrations for schema management
- **Input Validation**: Marshmallow schemas for request validation
- **Status Tracking**: Complete order lifecycle management with status enums

## Architecture Overview

The system follows a microservices-inspired architecture with clear separation of concerns:

- **API Layer** (`routes/`): REST endpoints for order operations
- **Business Logic** (`services/`): Order processing, payment, and inventory management
- **Data Layer** (`models/`): SQLAlchemy models and database interactions
- **Worker Layer** (`workers/`): Background processing with queue management
- **Utilities** (`utils/`): Logging and shared utilities

### Order Processing Flow

1. **Order Creation**: Client submits order with items and idempotency key
2. **Queue Enqueue**: Order is saved as PENDING and added to processing queue
3. **Inventory Check**: Background worker validates and reserves inventory
4. **Payment Processing**: Worker processes payment with external service
5. **Completion**: Order marked as COMPLETED or FAILED based on results

## Installation

### Prerequisites

- Python 3.8+
- pip

### Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd flask-assignment
```

2. Create a virtual environment:

```bash
python -m venv venv
```

3. Activate the virtual environment:

```bash
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Initialize the database:

```bash
flask db upgrade
```

## Usage

### Running the Application

Start the Flask development server:

```bash
python app.py
```

The API will be available at `http://localhost:5000`

### API Endpoints

#### Create Order

```http
POST /orders
Content-Type: application/json
Idempotency-Key: <unique-key>

{
  "items": [
    {"name": "item1", "quantity": 2},
    {"name": "item2", "quantity": 1}
  ]
}
```

**Response (201 Created):**

```json
{
  "id": "order-uuid",
  "items": [...],
  "status": "PENDING",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

#### Get Order

```http
GET /orders/{order_id}
```

#### List Orders

```http
GET /orders?page=1&limit=10&status=PENDING
```

#### Cancel Order

```http
POST /orders/{order_id}/cancel
```

### Order Statuses

- `PENDING`: Order created, waiting for processing
- `INVENTORY_PROCESSING`: Checking inventory availability
- `INVENTORY_RESERVED`: Inventory successfully reserved
- `PAYMENT_PROCESSING`: Processing payment
- `COMPLETED`: Order successfully fulfilled
- `FAILED`: Order failed after all retries
- `CANCELLED`: Order cancelled by user

## Configuration

### Environment Variables

- `FLASK_ENV`: Set to `development` for debug mode
- `DATABASE_URL`: Database connection string (defaults to SQLite)

### Constants

Located in `constants/order_constants.py`:

- `MAX_PAYMENT_RETRIES`: Maximum payment retry attempts (default: 3)
- `MAX_INVENTORY_RETRIES`: Maximum inventory retry attempts (default: 3)

## Development

### Database Migrations

Create a new migration:

```bash
flask db migrate -m "migration message"
```

Apply migrations:

```bash
flask db upgrade
```

### Testing

Run tests (if implemented):

```bash
pytest
```

### Logging

Logs are written to console with structured format including:

- Order lifecycle events
- Error conditions
- Retry attempts
- State transitions

## Design Decisions

### Asynchronous Processing

Orders are processed asynchronously to prevent API timeouts and improve user experience. The queue-based system ensures reliable processing even under high load.

### Idempotency

All order creation requests require an idempotency key to prevent duplicate orders from network retries or user mistakes.

### Retry Logic

Both payment and inventory operations include retry logic with exponential backoff to handle transient failures.

### Atomic Operations

Order cancellation uses atomic database updates to prevent race conditions between worker processing and user cancellation.

### Status Tracking

Comprehensive status tracking enables monitoring, debugging, and proper state management throughout the order lifecycle.

## Contributing

1. Follow the existing code structure and naming conventions
2. Add appropriate logging for new features
3. Include input validation for new endpoints
4. Update this README for API changes
5. Test thoroughly, especially edge cases and error conditions

## License

[Add license information]

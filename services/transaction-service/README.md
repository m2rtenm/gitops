# Transaction Service

Processes and tracks transactions between accounts. This service handles the creation and retrieval of all inter-account movements.

## Integration with Other Services

- **Account Service**: Validates source and destination accounts
- **Ledger Service**: Sends transaction events to ledger for immutable recording
- **Fraud Detection Service**: Transaction data is consumed for real-time fraud detection
- **Settlement Service**: Consumes transaction events for settlement and reconciliation

## API Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /ready` - Readiness check  
- `GET /metrics` - Prometheus metrics

### Transactions
- `POST /api/v1/transactions` - Create new transaction
- `GET /api/v1/transactions/{id}` - Get transaction details
- `GET /api/v1/transactions/account/{account_id}` - Get transactions for account
- `PUT /api/v1/transactions/{id}` - Update transaction
- `GET /api/v1/transactions/{id}/status` - Get transaction status

## Environment Variables

```bash
KAFKA_BROKERS=kafka:9092
KAFKA_TOPIC_TRANSACTIONS=fintech.transactions
KAFKA_TOPIC_EVENTS=fintech.transaction-events
KAFKA_CONSUMER_GROUP=transaction-service
POSTGRES_HOST=postgres-accounts
POSTGRES_PORT=5432
POSTGRES_DB=accounts_db
POSTGRES_USER=accounts_user
POSTGRES_PASSWORD=password
LOG_LEVEL=INFO
```

## Kafka Topics

**Publishes to:**
- `fintech.transactions` - Transaction data for other services
- `fintech.transaction-events` - Transaction state change events

**Consumes from:**
- (None directly; listens via events)

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python src/main.py

# Run tests
pytest tests/
```

## Docker

```bash
# Build
docker build -t fintech/transaction-service:1.0.0 .

# Run
docker run -p 8081:8080 \
  -e POSTGRES_HOST=localhost \
  -e KAFKA_BROKERS=localhost:9092 \
  fintech/transaction-service:1.0.0
```

## Database Schema

```sql
CREATE TABLE transactions (
  id SERIAL PRIMARY KEY,
  from_account_id BIGINT NOT NULL,
  to_account_id BIGINT NOT NULL,
  amount NUMERIC(19, 4) NOT NULL,
  currency VARCHAR(3) DEFAULT 'USD',
  status VARCHAR(20) DEFAULT 'PENDING',
  description TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_from_account ON transactions(from_account_id);
CREATE INDEX idx_to_account ON transactions(to_account_id);
CREATE INDEX idx_status ON transactions(status);
```

## Example Requests

### Create Transaction
```bash
curl -X POST http://localhost:8081/api/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "from_account_id": 1,
    "to_account_id": 2,
    "amount": 100.50,
    "currency": "USD",
    "description": "Payment for services"
  }'
```

### Get Transaction
```bash
curl http://localhost:8081/api/v1/transactions/1
```

### Get Account Transactions
```bash
curl http://localhost:8081/api/v1/transactions/account/1
```

## Data Flow

```
User/Client
    ↓
Account Service (validates accounts)
    ↓
Transaction Service (creates transaction)
    ├→ Publishes to fintech.transactions
    └→ Publishes to fintech.transaction-events
    ↓
Ledger Service (records in immutable ledger)
Fraud Detection Service (analyzes for fraud)
Settlement Service (prepares for settlement)
```

## Performance Considerations

- Use pagination for large transaction lists
- Indexes on `from_account_id`, `to_account_id`, and `status` for query performance
- Kafka guarantees ordering per account
- Connection pooling recommended for high volume

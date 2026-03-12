# Ledger Service

Maintains an immutable ledger of all transactions and provides accurate balance tracking. This is the source of truth for account balances and transaction history.

## Integration with Other Services

- **Transaction Service**: Consumes transaction events to record in ledger
- **Settlement Service**: Reads ledger entries for settlements and reconciliation
- **Fraud Detection Service**: Provides transaction history for pattern detection
- **Account Service**: Records balance changes from transactions

## API Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /metrics` - Prometheus metrics

### Ledger
- `POST /api/v1/ledger` - Record ledger entry
- `GET /api/v1/ledger/{id}` - Get ledger entry
- `GET /api/v1/ledger/account/{account_id}` - Get account ledger history

### Balances
- `GET /api/v1/balances/{account_id}` - Get account balance
- `PUT /api/v1/balances/{account_id}` - Update account balance
- `GET /api/v1/balances/{account_id}/reserved` - Get reserved balance

## Environment Variables

```bash
KAFKA_BROKERS=kafka:9092
KAFKA_TOPIC_LEDGER=fintech.ledger
KAFKA_TOPIC_EVENTS=fintech.ledger-events
KAFKA_CONSUMER_GROUP=ledger-service
POSTGRES_HOST=postgres-ledger
POSTGRES_PORT=5432
POSTGRES_DB=ledger_db
POSTGRES_USER=ledger_user
POSTGRES_PASSWORD=password
LOG_LEVEL=INFO
```

## Kafka Topics

**Publishes to:**
- `fintech.ledger` - Ledger entries for other services
- `fintech.ledger-events` - Ledger state change events

**Consumes from:**
- `fintech.transaction-events` - Transaction events from Transaction Service

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
docker build -t fintech/ledger-service:1.0.0 .

# Run
docker run -p 8082:8080 \
  -e POSTGRES_HOST=localhost \
  -e KAFKA_BROKERS=localhost:9092 \
  fintech/ledger-service:1.0.0
```

## Database Schema

```sql
-- Immutable ledger of all transactions
CREATE TABLE ledger (
  id BIGSERIAL PRIMARY KEY,
  transaction_id BIGINT UNIQUE NOT NULL,
  account_from BIGINT NOT NULL,
  account_to BIGINT NOT NULL,
  amount NUMERIC(19, 4) NOT NULL,
  currency VARCHAR(3) DEFAULT 'USD',
  status VARCHAR(20) DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT NOW(),
  settled_at TIMESTAMP
);

-- Account balance tracking with versioning
CREATE TABLE balances (
  id SERIAL PRIMARY KEY,
  account_id BIGINT UNIQUE NOT NULL,
  balance NUMERIC(19, 4) NOT NULL DEFAULT 0,
  reserved NUMERIC(19, 4) DEFAULT 0,
  last_updated TIMESTAMP DEFAULT NOW(),
  version BIGINT DEFAULT 1
);

CREATE INDEX idx_ledger_account_from ON ledger(account_from);
CREATE INDEX idx_ledger_account_to ON ledger(account_to);
CREATE INDEX idx_ledger_status ON ledger(status);
CREATE INDEX idx_balances_account ON balances(account_id);
```

## Example Requests

### Get Account Balance
```bash
curl http://localhost:8082/api/v1/balances/1
```

Response:
```json
{
  "account_id": 1,
  "balance": 5000.00,
  "reserved": 500.00,
  "available": 4500.00,
  "last_updated": "2026-03-12T21:30:00Z"
}
```

### Get Account Ledger History
```bash
curl http://localhost:8082/api/v1/ledger/account/1?limit=10&offset=0
```

## Key Characteristics

- **Immutable**: Ledger entries are never deleted or modified
- **Append-only**: Each transaction creates exactly one ledger entry
- **Versioned Balances**: Track balance versions for audit trails
- **Event-driven**: Updates triggered by transaction events

## Data Flow

```
Transaction Service publishes to fintech.transaction-events
    ↓
Ledger Service consumes event
    ↓
Records entry in ledger table (immutable)
    ↓
Updates balance table with new balance
    ↓
Publishes fintech.ledger-events
    ↓
Settlement Service, Fraud Detection Service consume
```

## Performance Considerations

- Ledger is append-only (no updates/deletes) - optimal for fast writes
- Balances use versioning for audit and concurrency control
- Indexes on account IDs for fast lookups
- Consider partitioning ledger table by date for very large datasets

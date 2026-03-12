# Settlement Service

Handles settlement and reconciliation of transactions. This service groups transactions into settlement batches, performs final reconciliation, and ensures all accounts are cleared.

## Integration with Other Services

- **Transaction Service**: Consumes transaction events for settlement
- **Ledger Service**: Reads ledger entries and balances for settlement calculations
- **Fraud Detection Service**: Waits for fraud clearance before settling
- **Account Service**: Updates final account balances post-settlement

## API Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /metrics` - Prometheus metrics

### Settlements
- `POST /api/v1/settlements` - Create settlement for transaction
- `GET /api/v1/settlements/{id}` - Get settlement details
- `GET /api/v1/settlements/batch/{batch_id}` - Get batch settlements
- `PUT /api/v1/settlements/{id}` - Update settlement status

### Settlement Batches
- `POST /api/v1/settlement-batches` - Create settlement batch
- `GET /api/v1/settlement-batches/{id}` - Get batch details
- `GET /api/v1/settlement-batches` - List batches (paginated)
- `PUT /api/v1/settlement-batches/{id}/reconcile` - Reconcile batch

## Environment Variables

```bash
KAFKA_BROKERS=kafka:9092
KAFKA_TOPIC_SETTLEMENT=fintech.settlement
KAFKA_TOPIC_EVENTS=fintech.settlement-events
KAFKA_CONSUMER_GROUP=settlement-service
POSTGRES_HOST=postgres-ledger
POSTGRES_PORT=5432
POSTGRES_DB=ledger_db
POSTGRES_USER=ledger_user
POSTGRES_PASSWORD=password
LOG_LEVEL=INFO
SETTLEMENT_BATCH_HOUR=23  # Hour to create batch (24-hour format)
RECONCILIATION_ENABLED=true
```

## Kafka Topics

**Publishes to:**
- `fintech.settlement` - Settlement notifications
- `fintech.settlement-events` - Settlement state change events

**Consumes from:**
- `fintech.transaction-events` - Transaction events
- `fintech.ledger-events` - Ledger confirmation events

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
docker build -t fintech/settlement-service:1.0.0 .

# Run
docker run -p 8083:8080 \
  -e POSTGRES_HOST=localhost \
  -e KAFKA_BROKERS=localhost:9092 \
  -e SETTLEMENT_BATCH_HOUR=23 \
  fintech/settlement-service:1.0.0
```

## Database Schema

```sql
-- Individual settlement records
CREATE TABLE settlements (
  id SERIAL PRIMARY KEY,
  transaction_id BIGINT UNIQUE NOT NULL,
  settlement_date DATE NOT NULL,
  settlement_time TIMESTAMP DEFAULT NOW(),
  amount NUMERIC(19, 4) NOT NULL,
  status VARCHAR(20) DEFAULT 'PENDING',
  reconciliation_status VARCHAR(20) DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT NOW(),
  settled_at TIMESTAMP
);

-- Batch settlements (daily/daily grouping)
CREATE TABLE settlement_batch (
  id SERIAL PRIMARY KEY,
  batch_date DATE NOT NULL,
  batch_time TIMESTAMP DEFAULT NOW(),
  total_amount NUMERIC(19, 4) NOT NULL,
  transaction_count INT NOT NULL,
  status VARCHAR(20) DEFAULT 'PENDING'
);

CREATE INDEX idx_settlements_date ON settlements(settlement_date);
CREATE INDEX idx_settlements_status ON settlements(status);
CREATE INDEX idx_settlements_transaction ON settlements(transaction_id);
CREATE INDEX idx_batch_date ON settlement_batch(batch_date);
CREATE INDEX idx_batch_status ON settlement_batch(status);
```

## Example Requests

### Create Settlement Batch
```bash
curl -X POST http://localhost:8083/api/v1/settlement-batches \
  -H "Content-Type: application/json" \
  -d '{
    "batch_date": "2026-03-12",
    "settlement_ids": [1, 2, 3, 4, 5]
  }'
```

### Get Settlement Details
```bash
curl http://localhost:8083/api/v1/settlements/1
```

### Reconcile Batch
```bash
curl -X PUT http://localhost:8083/api/v1/settlement-batches/1/reconcile \
  -H "Content-Type: application/json" \
  -d '{
    "reconciliation_notes": "Daily reconciliation completed"
  }'
```

## Settlement States

```
PENDING → INITIATED → PROCESSING → SETTLED → RECONCILED
           ↓
         ERROR (can retry)
```

## Data Flow

```
Transaction Service publishes fintech.transaction-events
    ↓
Settlement Service consumes
    ↓
Groups into daily batches
    ↓
Checks Ledger Service for confirmation
    ↓
Checks Fraud Detection Service (no pending alerts)
    ↓
Creates settlements
    ↓
Initiates settlement process
    ↓
Publishes fintech.settlement-events (settled)
    ↓
Daily reconciliation at configured hour
    ↓
Publishes fintech.settlement-events (reconciled)
```

## Key Characteristics

- **Batch Processing**: Groups transactions by settlement date
- **Two-Phase Settlement**: Initiated → Settled → Reconciled
- **Scheduled Batching**: Automatic daily batch creation
- **Reconciliation**: Verifies all transactions settled correctly

## Performance Considerations

- Batching reduces per-transaction overhead
- Indexes on date/status for fast batch queries
- Settlement timestamp tracking for audit
- Separates settlement from reconciliation for flexibility

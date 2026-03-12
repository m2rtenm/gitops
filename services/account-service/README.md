# Account Service

Manages customer accounts and their profiles.

## API Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /metrics` - Prometheus metrics

### Accounts
- `POST /api/v1/accounts` - Create new account
- `GET /api/v1/accounts/{id}` - Get account details
- `GET /api/v1/accounts/{id}/balance` - Get account balance

## Environment Variables

```bash
KAFKA_BROKERS=kafka:9092
KAFKA_TOPIC_ACCOUNTS=fintech.accounts
KAFKA_TOPIC_EVENTS=fintech.account-events
KAFKA_CONSUMER_GROUP=account-service
POSTGRES_HOST=postgres-accounts
POSTGRES_PORT=5432
POSTGRES_DB=accounts_db
POSTGRES_USER=accounts_user
POSTGRES_PASSWORD=password
LOG_LEVEL=INFO
```

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
docker build -t fintech/account-service:1.0.0 .

# Run
docker run -p 8080:8080 \
  -e POSTGRES_HOST=localhost \
  -e KAFKA_BROKERS=localhost:9092 \
  fintech/account-service:1.0.0
```

## Database Schema

```sql
CREATE TABLE accounts (
  id SERIAL PRIMARY KEY,
  customer_id BIGINT UNIQUE NOT NULL,
  account_number VARCHAR(20) UNIQUE NOT NULL,
  account_type VARCHAR(50) NOT NULL,
  balance NUMERIC(19, 4) DEFAULT 0,
  currency VARCHAR(3) DEFAULT 'USD',
  status VARCHAR(20) DEFAULT 'ACTIVE',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE account_holders (
  id BIGSERIAL PRIMARY KEY,
  account_id BIGINT NOT NULL REFERENCES accounts(id),
  holder_name VARCHAR(255) NOT NULL,
  holder_email VARCHAR(255),
  holder_phone VARCHAR(20),
  created_at TIMESTAMP DEFAULT NOW()
);
```

## Example Requests

### Create Account
```bash
curl -X POST http://localhost:8080/api/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": 12345,
    "account_number": "ACC-001",
    "account_type": "CHECKING"
  }'
```

### Get Account
```bash
curl http://localhost:8080/api/v1/accounts/1
```

### Get Balance
```bash
curl http://localhost:8080/api/v1/accounts/1/balance
```

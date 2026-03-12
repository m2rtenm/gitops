#!/bin/bash
set -e

echo "================================"
echo "Fintech System - Service Tests"
echo "================================"
echo ""

BASE_URL="${BASE_URL:-http://localhost:8001}"
SERVICE="${SERVICE:-account-service}"
NAMESPACE="${NAMESPACE:-fintech}"

echo "Testing $SERVICE at $BASE_URL"
echo ""

# Check if curl can reach the service
if ! curl -s -m 2 "$BASE_URL/health" > /dev/null 2>&1; then
    echo "ERROR: Cannot reach $BASE_URL"
    echo ""
    echo "To run tests with Kubernetes, set up port-forward first:"
    echo "  kubectl port-forward svc/account-service-base-service 8001:8080 -n $NAMESPACE &"
    echo ""
    echo "Or for docker-compose local testing:"
    echo "  make start-local"
    echo ""
    exit 1
fi

# Test health endpoint
echo "[1/5] Testing health endpoint..."
HEALTH=$(curl -s "$BASE_URL/health")
echo "$HEALTH" | jq . 2>/dev/null || echo "$HEALTH"
echo ""

# Test readiness endpoint
echo "[2/5] Testing readiness endpoint..."
READY=$(curl -s "$BASE_URL/ready")
echo "$READY" | jq . 2>/dev/null || echo "$READY"
echo ""

# Test create account
echo "[3/5] Creating test account..."
ACCOUNT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/accounts" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": 12345,
    "account_number": "TEST-ACC-001",
    "account_type": "CHECKING"
  }')

if echo "$ACCOUNT_RESPONSE" | grep -q "error\|error\|Error"; then
    echo "ERROR creating account:"
    echo "$ACCOUNT_RESPONSE" | jq . 2>/dev/null || echo "$ACCOUNT_RESPONSE"
    exit 1
fi

echo "$ACCOUNT_RESPONSE" | jq . 2>/dev/null || echo "$ACCOUNT_RESPONSE"
ACCOUNT_ID=$(echo "$ACCOUNT_RESPONSE" | jq -r '.id // empty' 2>/dev/null)

if [ -z "$ACCOUNT_ID" ] || [ "$ACCOUNT_ID" = "null" ]; then
    echo "ERROR: Could not extract account ID from response"
    exit 1
fi

echo "Created account ID: $ACCOUNT_ID"
echo ""

# Test get account
echo "[4/5] Getting account details..."
GET_ACCOUNT=$(curl -s "$BASE_URL/api/v1/accounts/$ACCOUNT_ID")
echo "$GET_ACCOUNT" | jq . 2>/dev/null || echo "$GET_ACCOUNT"
echo ""

# Test get balance
echo "[5/5] Getting account balance..."
BALANCE=$(curl -s "$BASE_URL/api/v1/accounts/$ACCOUNT_ID/balance")
echo "$BALANCE" | jq . 2>/dev/null || echo "$BALANCE"
echo ""

echo "================================"
echo "Tests completed successfully!"
echo "================================"

#!/bin/bash
set -e

echo "================================"
echo "Fintech System - Local Test"
echo "================================"
echo ""

BASE_URL="${BASE_URL:-http://localhost:8001}"
SERVICE="${SERVICE:-account-service}"

echo "Testing $SERVICE at $BASE_URL"
echo ""

# Test health endpoint
echo "[1/5] Testing health endpoint..."
curl -s "$BASE_URL/health" | jq .
echo ""

# Test readiness endpoint
echo "[2/5] Testing readiness endpoint..."
curl -s "$BASE_URL/ready" | jq .
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
echo "$ACCOUNT_RESPONSE" | jq .
ACCOUNT_ID=$(echo "$ACCOUNT_RESPONSE" | jq -r '.id')
echo "Created account ID: $ACCOUNT_ID"
echo ""

# Test get account
echo "[4/5] Getting account details..."
curl -s "$BASE_URL/api/v1/accounts/$ACCOUNT_ID" | jq .
echo ""

# Test get balance
echo "[5/5] Getting account balance..."
curl -s "$BASE_URL/api/v1/accounts/$ACCOUNT_ID/balance" | jq .
echo ""

echo "================================"
echo "Tests completed successfully!"
echo "================================"

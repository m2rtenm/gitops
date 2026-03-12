#!/bin/bash
set -e

DOCKER_REGISTRY="${DOCKER_REGISTRY:-fintech}"
DOCKER_TAG="${DOCKER_TAG:-1.0.0}"

SERVICES=(
  "account-service"
  "transaction-service"
  "ledger-service"
  "settlement-service"
  "fraud-detection-service"
)

echo "================================"
echo "Building Fintech Services"
echo "================================"
echo ""
echo "Registry: $DOCKER_REGISTRY"
echo "Tag: $DOCKER_TAG"
echo ""

for service in "${SERVICES[@]}"; do
  echo "Building $service..."
  cd "services/$service"
  
  docker build -t "$DOCKER_REGISTRY/$service:$DOCKER_TAG" .
  
  echo "  ✓ Built $DOCKER_REGISTRY/$service:$DOCKER_TAG"
  echo ""
  
  cd ../..
done

echo "================================"
echo "All services built successfully!"
echo "================================"
echo ""
echo "To push to registry:"
for service in "${SERVICES[@]}"; do
  echo "  docker push $DOCKER_REGISTRY/$service:$DOCKER_TAG"
done

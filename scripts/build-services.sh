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

# If using minikube, you may wish to build into minikube's docker
# daemon so the cluster can pull the images without pushing. Docker Desktop
# does not require this step because it uses the same engine as the host.
if command -v minikube >/dev/null 2>&1; then
  if minikube status >/dev/null 2>&1; then
    echo "Note: images built in local docker daemon."
    echo "If deploying to Minikube, run:"
    echo "  eval \$(minikube docker-env)"
    echo "  ./scripts/build-services.sh"              
  fi
fi

echo "To push to external registry (if not using minikube):"
for service in "${SERVICES[@]}"; do
  echo "  docker push $DOCKER_REGISTRY/$service:$DOCKER_TAG"
done

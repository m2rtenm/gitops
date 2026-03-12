#!/bin/bash
set -e

NAMESPACE_NS="fintech-ns"
KAFKA_RELEASE="fintech-kafka"
PG_ACCOUNTS="postgres-accounts"
PG_LEDGER="postgres-ledger"
PG_AUDIT="postgres-audit"
PROJECT_RELEASE="fintech-project"
APPSET_RELEASE="fintech-appset"

GITOPS_REPO="${GITOPS_REPO:-https://github.com/m2rtenm/gitops}"
SERVICES_REPO="${SERVICES_REPO:-https://github.com/m2rtenm/fintech-services}"

echo "================================"
echo "Fintech System Setup"
echo "================================"
echo ""
echo "GitOps Repo: $GITOPS_REPO"
echo "Services Repo: $SERVICES_REPO"
echo ""

# ensure Kafka operator (Strimzi) is available for KafkaTopic CRDs
if ! kubectl get crd kafkatopics.kafka.strimzi.io >/dev/null 2>&1; then
  echo "[0/6] Strimzi Kafka CRD not found, installing Strimzi operator..."
  helm repo add strimzi https://strimzi.io/charts || true
  helm upgrade --install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
    --namespace strimzi-system --create-namespace --wait
else
  echo "[0/6] Strimzi Kafka CRD already present"
fi

echo ""

# 1. Create namespaces
echo "[1/6] Creating namespaces..."
helm upgrade --install $NAMESPACE_NS charts/namespace \
  -f fintech/argocd/values-namespaces.yaml \
  --wait

# 2. Install Kafka topics
echo "[2/6] Creating Kafka topics..."
helm upgrade --install $KAFKA_RELEASE charts/kafka-topics \
  -f fintech/infra/values-kafka-topics.yaml \
  -n fintech-infra \
  --create-namespace \
  --wait

# 3. Install Postgres databases
echo "[3/6] Installing Postgres databases..."
helm upgrade --install $PG_ACCOUNTS charts/postgres-database \
  -f fintech/infra/values-postgres-accounts.yaml \
  -n fintech-infra \
  --create-namespace \
  --wait

helm upgrade --install $PG_LEDGER charts/postgres-database \
  -f fintech/infra/values-postgres-ledger.yaml \
  -n fintech-infra \
  --create-namespace \
  --wait

helm upgrade --install $PG_AUDIT charts/postgres-database \
  -f fintech/infra/values-postgres-audit.yaml \
  -n fintech-infra \
  --create-namespace \
  --wait

# 4. Create ArgoCD project
echo "[4/6] Creating ArgoCD project..."
helm upgrade --install $PROJECT_RELEASE charts/argocd-project \
  -f fintech/argocd/values-project.yaml \
  -n argocd \
  --create-namespace \
  --wait

# 5. Create ApplicationSet
echo "[5/6] Creating ApplicationSet..."
helm upgrade --install $APPSET_RELEASE charts/argocd-appset \
  -f fintech/argocd/values-appset.yaml \
  -n argocd \
  --create-namespace \
  --wait

# 6. Deploy individual services
echo "[6/6] Deploying fintech services..."
for service in account-service transaction-service ledger-service settlement-service fraud-detection-service; do
  echo "  - Deploying $service..."
  helm upgrade --install $service charts/base-service \
    -f fintech/services/$service/values.yaml \
    -n fintech \
    --create-namespace \
    --wait=false
done

echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "Check status:"
echo "  kubectl get pods -n fintech"
echo "  kubectl get pods -n fintech-infra"
echo ""
echo "View logs:"
echo "  kubectl logs -f deployment/account-service -n fintech"
echo ""
echo "Port-forward to test:"
echo "  kubectl port-forward svc/account-service -n fintech 8080:8080"

# Fintech System - Complete Setup Guide

> **Note for Docker Desktop users:** the Docker Desktop Kubernetes cluster
> shares the host’s container runtime, so any images you build locally are
> immediately available to the cluster. No `minikube docker-env` step is
> needed. If you switch to minikube later, follow the instructions below to
> point your shell at minikube’s daemon.

This guide walks through setting up and deploying the complete fintech banking system.

## 📋 Table of Contents
1. [Local Development (Docker Compose)](#local-development)
2. [Kubernetes Deployment](#kubernetes-deployment)
3. [ArgoCD Setup](#argocd-setup)
4. [Service Deployment](#service-deployment)
5. [Testing](#testing)
6. [Troubleshooting](#troubleshooting)

---

## Local Development

> **PVC warnings**
> If a PostgreSQL Pod remains in `Pending` with `Pod has unbound
> immediate PersistentVolumeClaims`, it means the PVC could not be
> provisioned. This usually happens when the `storageClassName` in the
> values files (default `standard`) doesn't exist on your cluster. You
> can either create the class in your cluster, or set
> `persistence.storageClassName: ""` in the appropriate
> `fintech/infra/values-postgres-*.yaml` file to use the default class.
> After adjusting values delete any stuck PVCs and rerun
> `make setup-fintech`.

## Local Development

### Quick Start with Docker Compose

Perfect for testing services locally without Kubernetes.

```bash
# Start all services
make start-local

# Postgres containers include healthchecks; service containers depend on
# healthy databases and the microservices themselves retry until the
# database accepts connections. If you see connection errors in logs,
# give the database a few seconds and the service will recover.

# Check logs
docker-compose logs -f

# Stop services
make stop-local
```

Services will be available at:
- Account Service: http://localhost:8001
- Transaction Service: http://localhost:8002
- Ledger Service: http://localhost:8003
- Settlement Service: http://localhost:8004
- Fraud Detection: http://localhost:8005

### Testing Services Locally

```bash
# Create an account
curl -X POST http://localhost:8001/api/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": 12345,
    "account_number": "TEST-001",
    "account_type": "CHECKING"
  }'

# Check health
curl http://localhost:8001/health
```

---

## Kubernetes Deployment

### Prerequisites

Install required tools:

```bash
# macOS with Homebrew
brew install minikube kubectl helm

# Linux
curl -LO https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### Start Minikube

```bash
# Create cluster with sufficient resources
minikube start --cpus 4 --memory 8192 --profile fintech

# Set profile
minikube profile set fintech

# Enable metrics server (for HPA)
minikube addons enable metrics-server

# Enable ingress (optional)
minikube addons enable ingress
```

### Build & Push Service Images

Before deploying to Kubernetes, ensure the container images referenced by the
Helm values have been built and are accessible from the cluster. By default
those values point at `fintech/<service>:1.0.0`.

```bash
# build locally
make build-services

# when using minikube, instruct docker to build inside the cluster daemon:
eval $(minikube docker-env)
make build-services

# if you are using an external registry, push the images afterwards:
# docker push fintech/account-service:1.0.0  # etc.
```

> `make setup-fintech` does **not** build images; run the above step first or
your pods will fail with `ImagePullBackOff`.

### Install Required Components

Before deploying fintech, ensure Kafka and other operator are available:

```bash
# Install Strimzi Kafka Operator (if using Kafka)
# You can use the make target for convenience:
#     make install-strimzi
helm repo add strimzi https://strimzi.io/charts
helm install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
  --namespace strimzi-system --create-namespace

# Or use existing Kafka cluster
```

---

## ArgoCD Setup

### Install ArgoCD

```bash
# Run the installation script
make install-argocd

# Or manually
scripts/install-argocd.sh
```

This will:
1. Create `argocd` namespace
2. Deploy ArgoCD components
3. Wait for server to be ready
4. Output initial admin password

### Access ArgoCD

```bash
# Port-forward to ArgoCD
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Open browser
# https://localhost:8080
# Username: admin
# Password: (from install script output)
```

### Change Admin Password

```bash
argocd account update-password \
  --account admin \
  --current-password <current> \
  --new-password <new>
```

---

## Service Deployment

### Step 1: Build Docker Images

If using local Docker registry (minikube):

```bash
# Point Docker to minikube
eval $(minikube docker-env)

# Build images
make build-services

# Or individually
cd services/account-service
docker build -t fintech/account-service:1.0.0 .
```

### Step 2: Create Namespaces

```bash
helm install fintech-ns charts/namespace \
  -f fintech/argocd/values-namespaces.yaml
```

Verify:
```bash
kubectl get namespaces
# Should show: fintech, fintech-infra
```

### Step 3: Deploy Infrastructure

#### Kafka Topics

```bash
helm install fintech-kafka charts/kafka-topics \
  -f fintech/infra/values-kafka-topics.yaml \
  -n fintech-infra \
  --wait
```

Verify:
```bash
kubectl get kafkatopic -n fintech-infra
```

#### PostgreSQL Databases

```bash
# Database 1: Accounts
helm install postgres-accounts charts/postgres-database \
  -f fintech/infra/values-postgres-accounts.yaml \
  -n fintech-infra \
  --wait

# Database 2: Ledger
helm install postgres-ledger charts/postgres-database \
  -f fintech/infra/values-postgres-ledger.yaml \
  -n fintech-infra \
  --wait

# Database 3: Audit
helm install postgres-audit charts/postgres-database \
  -f fintech/infra/values-postgres-audit.yaml \
  -n fintech-infra \
  --wait
```

Verify:
```bash
kubectl get statefulset -n fintech-infra
kubectl get svc -n fintech-infra
```

### Step 4: Deploy Microservices

#### Option A: Using Setup Script (Recommended)

```bash
make setup-fintech
# Or
scripts/setup-fintech.sh
```

This will automatically deploy all 5 services.

#### Option B: Manual Deployment

```bash
helm install account-service charts/base-service \
  -f fintech/services/account-service/values.yaml \
  -n fintech \
  --create-namespace \
  --wait

# Repeat for other services...
helm install transaction-service charts/base-service \
  -f fintech/services/transaction-service/values.yaml \
  -n fintech --wait

# ... and so on
```

### Step 5: Configure ArgoCD

Create the ArgoCD project:

```bash
helm install fintech-project charts/argocd-project \
  -f fintech/argocd/values-project.yaml \
  -n argocd
```

Create the ApplicationSet:

```bash
helm install fintech-appset charts/argocd-appset \
  -f fintech/argocd/values-appset.yaml \
  -n argocd
```

View in ArgoCD:
```bash
argocd app list
```

---

## Testing

### Health Checks

```bash
# Port-forward to service
kubectl port-forward svc/account-service -n fintech 8080:8080

# Test health
curl http://localhost:8080/health

# Test readiness
curl http://localhost:8080/ready

# View metrics
curl http://localhost:8080/metrics | head -20
```

### API Testing

```bash
# Create Account
curl -X POST http://localhost:8080/api/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": 100,
    "account_number": "ACC-100",
    "account_type": "CHECKING"
  }'

# Get Account (replace {id} with actual ID)
curl http://localhost:8080/api/v1/accounts/1

# Get Balance
curl http://localhost:8080/api/v1/accounts/1/balance
```

### Run Test Suite

```bash
make test-services
# Or
scripts/test-services.sh
```

---

## Monitoring & Debugging

### Check Pod Status

```bash
# Get all pods
kubectl get pods -n fintech
kubectl get pods -n fintech-infra

# Detailed pod info
kubectl describe pod <pod-name> -n fintech

# View logs
kubectl logs deployment/account-service -n fintech
kubectl logs -f deployment/account-service -n fintech  # Follow
```

### Database Access

```bash
# Connect to accounts DB
kubectl run pg-client -it --rm --image=postgres:15-alpine -- \
  psql -h postgres-accounts -U accounts_user -d accounts_db

# Inside psql:
# \dt - List tables
# SELECT * FROM accounts; - Query
# \q - Quit
```

### Kafka Inspection

```bash
# List topics
kubectl get kafkatopic -n fintech-infra

# Check Kafka logs
kubectl logs -n fintech-infra -l app=kafka
```

### ArgoCD Status

```bash
# Get app status
argocd app get fintech-account-service

# Sync app
argocd app sync fintech-account-service

# Watch sync
argocd app watch fintech-account-service
```

---

## Scaling Services

### Horizontal Pod Autoscaler

Autoscaling is enabled by default. Check HPA status:

```bash
kubectl get hpa -n fintech

# Watch HPA
kubectl get hpa -n fintech -w
```

### Manual Scaling

```bash
# Scale account service to 5 replicas
kubectl scale deployment account-service -n fintech --replicas=5

# Check
kubectl get pods -l app.kubernetes.io/name=account-service -n fintech | wc -l
```

### Update HPA Settings

Edit service values file and redeploy:

```yaml
# fintech/services/account-service/values.yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 15
  targetCPUUtilizationPercentage: 70
```

Then:
```bash
helm upgrade account-service charts/base-service \
  -f fintech/services/account-service/values.yaml \
  -n fintech --wait
```

---

## Updating Services

### Update Service Code

1. Modify service code in `services/<service>/src/`
2. Rebuild Docker image:
   ```bash
   cd services/account-service
   docker build -t fintech/account-service:1.0.1 .
   ```
3. Update version in values file:
   ```yaml
   # fintech/services/account-service/values.yaml
   image:
     tag: "1.0.1"
   ```
4. Redeploy:
   ```bash
   helm upgrade account-service charts/base-service \
     -f fintech/services/account-service/values.yaml \
     -n fintech --wait
   ```

---

## Troubleshooting

### Services not starting

```bash
# Check pod events
kubectl describe pod <pod-name> -n fintech

# Check resource limits
kubectl get resourcequota -n fintech

# Increase minikube resources if needed
minikube start --cpus 6 --memory 12288
```

### Database connection errors

```bash
# Verify database is running
kubectl get statefulset -n fintech-infra

# Check database logs
kubectl logs statefulset/postgres-accounts -n fintech-infra

# Verify service DNS
kubectl exec deployment/account-service -n fintech -- \
  nslookup postgres-accounts.fintech-infra
```

### Kafka connection issues

```bash
# Check Kafka broker
kubectl get pod -n fintech-infra | grep kafka

# Check Kafka logs
kubectl logs -n fintech-infra deployment/kafka-broker

# Verify topic creation
kubectl get kafkatopic -n fintech-infra
```

### ArgoCD sync failing

```bash
# Get application details
argocd app describe fintech-account-service

# Check ArgoCD logs
kubectl logs -f deployment/argocd-server -n argocd

# Force refresh
argocd app set fintech-account-service -p image.tag=1.0.1
```

### Memory/CPU issues

```bash
# Monitor resource usage
kubectl top nodes
kubectl top pods -n fintech

# Edit resource limits
# Edit fintech/services/<service>/values.yaml:
# resources:
#   limits:
#     cpu: 1000m      # Increase
#     memory: 1024Mi  # Increase
```

---

## Cleanup

### Remove Services

```bash
# Remove individual service
helm uninstall account-service -n fintech

# Remove all fintech components
make clean

# Full cleanup (includes ArgoCD)
make full-clean
```

---

## Next Steps

1. **Secure the setup**:
   - Enable TLS for ArgoCD
   - Use Kubernetes Secrets for passwords
   - Configure RBAC roles

2. **Add monitoring**:
   - Install Prometheus
   - Deploy Grafana
   - Configure AlertManager

3. **Production deployment**:
   - Use external Kafka cluster
   - Use managed PostgreSQL
   - Use private container registry
   - Set up backup/restore

4. **CI/CD pipeline**:
   - Build images on commits
   - Run automated tests
   - Deploy via ArgoCD

---

## Support

For more information, see:
- [Main README](./README.md)
- [Service Documentation](./services/)
- [Helm Chart Values](./charts/)

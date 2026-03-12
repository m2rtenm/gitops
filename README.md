# Fintech Banking System - GitOps Architecture

A complete fintech banking system built with microservices, Kubernetes, ArgoCD, Kafka, and PostgreSQL databases.

## 🏗️ Project Structure

```
gitops/
├── charts/                      # Helm chart templates
│   ├── base-service/           # Template for microservices
│   ├── postgres-database/      # Template for Postgres
│   ├── kafka-topics/           # Template for Kafka topics
│   └── argocd-*                # ArgoCD templates
├── services/                    # Microservices source code
│   ├── account-service/        # Account management
│   ├── transaction-service/    # Transaction processing
│   ├── ledger-service/         # Immutable ledger
│   ├── settlement-service/     # Settlement & reconciliation
│   └── fraud-detection-service/ # Fraud detection engine
├── fintech/
│   ├── services/               # Service values files
│   ├── infra/                  # Infrastructure values
│   └── argocd/                 # ArgoCD configuration
└── scripts/                     # Utility scripts
    ├── install-argocd.sh       # Install ArgoCD
    ├── setup-fintech.sh        # Deploy fintech system
    └── build-services.sh       # Build Docker images
```

## 🏦 Microservices

### 1. Account Service
Account management and customer profiles.
- **Port**: 8080
- **Database**: postgres-accounts
- **Kafka Topics**: `fintech.accounts`, `fintech.account-events`
- **Endpoints**:
  - `POST /api/v1/accounts` - Create account
  - `GET /api/v1/accounts/{id}` - Get account
  - `GET /api/v1/accounts/{id}/balance` - Get balance

### 2. Transaction Service
Transaction processing and history.
- **Port**: 8080
- **Database**: postgres-accounts
- **Kafka Topics**: `fintech.transactions`, `fintech.transaction-events`
- **Endpoints**:
  - `POST /api/v1/transactions` - Create transaction
  - `GET /api/v1/transactions/{id}` - Get transaction
  - `GET /api/v1/accounts/{id}/transactions` - List transactions

### 3. Ledger Service
Immutable financial ledger and balance management.
- **Port**: 8080
- **Database**: postgres-ledger
- **Kafka Topics**: `fintech.ledger`, `fintech.ledger-events`
- **Endpoints**:
  - `POST /api/v1/ledger` - Create ledger entry
  - `GET /api/v1/ledger/{id}` - Get ledger entry (read-only)
  - `GET /api/v1/accounts/{id}/balance` - Get account balance

### 4. Settlement Service
Transaction settlement and reconciliation.
- **Port**: 8080
- **Database**: postgres-ledger
- **Kafka Topics**: `fintech.settlement`, `fintech.settlement-events`
- **Endpoints**:
  - `POST /api/v1/settlements` - Create settlement
  - `GET /api/v1/settlements/{id}` - Get settlement
  - `GET /api/v1/settlements/batch` - Get batch summary

### 5. Fraud Detection Service
Real-time fraud detection and prevention.
- **Port**: 8080
- **Database**: postgres-audit
- **Kafka Topics**: `fintech.transactions` (consumer), `fintech.fraud-alerts` (producer)
- **Endpoints**:
  - `POST /api/v1/analyze` - Analyze transaction
  - `GET /api/v1/alerts` - Get fraud alerts
  - `POST /api/v1/alerts/{id}/review` - Review alert

## 📋 Prerequisites

The examples below assume a Kubernetes context named `minikube` or
`docker-desktop`. Docker Desktop’s built-in cluster uses the same Docker
engine as your host, so you can build images locally and the cluster will
see them without further configuration. For minikube you need to configure
`docker-env` as shown.

- **minikube** (or any Kubernetes cluster)
- **kubectl** 1.24+
- **helm** 3.10+
- **Docker** (for building images)
- **Kafka** (Strimzi operator recommended)
- **PostgreSQL** (via Helm)

## 🚀 Quick Start

### 1. Start Minikube

```bash
minikube start --cpus 4 --memory 8192 --profile fintech
minikube profile set fintech
```

### 2. Install ArgoCD

```bash
cd gitops
scripts/install-argocd.sh
```

Access ArgoCD:
```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```
- URL: https://localhost:8080
- Username: admin
- Password: (from the script output)

### 3. Setup Fintech System

> **PVC issue**: If the `postgres-accounts` release stays in
> `pending-install` because its PVC can't bind, make sure your cluster has a
> storage class matching `persistence.storageClassName` (defaults to
> `standard`). For minikube you can leave the field blank to use the default
> class – the values files ship with `storageClassName: ""` for this reason.

### 3. Build & Push Images (required before deployment)

The Kubernetes cluster must be able to pull the service images listed in the
`fintech/services/*/values.yaml` files. By default they reference
`fintech/<service>:1.0.0`.

```bash
# build locally; will also work with minikube if you run in its docker-env
make build-services
# if using an external registry:
#   docker push fintech/account-service:1.0.0
#   docker push fintech/transaction-service:1.0.0
#   ...
```

If you are deploying to **minikube**, switch the Docker environment so the
cluster can see the freshly-built images instead of pulling from the network:

```bash
eval $(minikube docker-env)
make build-services
```

> **Note:** `make setup-fintech` does not build images; run the build step first
> or the pods will enter `ImagePullBackOff`.

### 4. Setup Fintech System

```bash
scripts/setup-fintech.sh
```

This will:
- Create `fintech` and `fintech-infra` namespaces
- Deploy Kafka topics
- Deploy PostgreSQL databases
- Create ArgoCD project and ApplicationSet
- Deploy all 5 microservices

### 4. Verify Deployment

```bash
# Check namespaces
kubectl get namespaces

# Check services
kubectl get pods -n fintech
kubectl get pods -n fintech-infra

# Check services
kubectl get svc -n fintech
```

## 🏗️ Building and Deploying Services

### Build Docker Images

```bash
cd gitops
scripts/build-services.sh
```

Or build individual service:
```bash
cd services/account-service
docker build -t fintech/account-service:1.0.0 .
```

### Push to Registry

```bash
docker push fintech/account-service:1.0.0
docker push fintech/transaction-service:1.0.0
docker push fintech/ledger-service:1.0.0
docker push fintech/settlement-service:1.0.0
docker push fintech/fraud-detection-service:1.0.0
```

### Update Service Image in Values

Edit the service values file and update the image tag:

```yaml
# fintech/services/account-service/values.yaml
image:
  repository: your-registry/fintech/account-service
  tag: "1.0.1"  # Change tag
```

Then re-apply:
```bash
helm upgrade account-service charts/base-service \
  -f fintech/services/account-service/values.yaml \
  -n fintech
```

## 🔄 Kafka Topics

The system creates 9 Kafka topics:

| Topic | Partitions | Purpose |
|-------|-----------|---------|
| `fintech.accounts` | 3 | Account state |
| `fintech.account-events` | 3 | Account changes |
| `fintech.transactions` | 5 | Transaction events |
| `fintech.transaction-events` | 3 | Transaction updates |
| `fintech.ledger` | 3 | Ledger entries (1-year retention) |
| `fintech.ledger-events` | 3 | Ledger updates |
| `fintech.settlement` | 3 | Settlement records |
| `fintech.settlement-events` | 3 | Settlement status |
| `fintech.fraud-alerts` | 3 | Fraud detection alerts |

## 📊 Databases

### postgres-accounts
- **Database**: `accounts_db`
- **User**: `accounts_user`
- **Tables**:
  - `accounts` - Customer accounts
  - `account_holders` - Account holder information

### postgres-ledger
- **Database**: `ledger_db`
- **User**: `ledger_user`
- **Tables**:
  - `transaction_ledger` - Immutable transaction log
  - `balances` - Current account balances

### postgres-audit
- **Database**: `audit_db`
- **User**: `audit_user`
- **Tables**:
  - `fraud_alerts` - Fraud detection alerts
  - `transaction_audit` - Transaction audit logs

## 🧪 Testing Services

### Port-Forward to Service

```bash
kubectl port-forward svc/account-service -n fintech 8080:8080
```

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

### Check Health

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl http://localhost:8080/metrics
```

## 🔍 Monitoring

All services expose Prometheus metrics on port 9090:
```bash
curl http://localhost:9090/metrics
```

Key metrics:
- `*_created_total` - Counter for created items
- `*_errors_total` - Error counter
- `*_request_duration_seconds` - Request latency histogram

## 🛠️ Helm Commands

### List Releases

```bash
helm list -n fintech
helm list -n fintech-infra
helm list -n argocd
```

### Upgrade Release

```bash
helm upgrade account-service charts/base-service \
  -f fintech/services/account-service/values.yaml \
  -n fintech \
  --wait
```

### Delete Release

```bash
helm uninstall account-service -n fintech
helm uninstall fintech-ns  # Delete namespaces
```

## 📝 ArgoCD Configuration

The system uses ArgoCD's ApplicationSet to manage services:

- **Project**: `fintech`
- **AppSet**: `fintech-services`
- **Generators**: List-based generator with 5 services
- **Sync Policy**: Automated (prune + self-heal)

### View Applications in ArgoCD

```bash
argocd app list
```

### Check Sync Status

```bash
argocd app get fintech-account-service
```

### Force Sync

```bash
argocd app sync fintech-account-service
```

## 🔐 Security

Current setup is for local development. For production:

1. **Enable TLS for ArgoCD**:
   - Remove `server.insecure=true` from ConfigMap
   - Generate proper TLS certificates

2. **Enable Kafka authentication**:
   - Configure SASL/SSL in Kafka broker
   - Update connection strings

3. **Enable PostgreSQL authentication**:
   - Set strong passwords in environment variables
   - Use secrets instead of hardcoded credentials
   - Enable SSL connections

4. **Network Policies**:
   - Enable in `fintech/services/*/values.yaml`
   - Restrict inter-service communication

5. **RBAC**:
   - Create proper Kubernetes RBAC roles
   - Use service accounts for each service

## 🐛 Troubleshooting

### Services not starting

```bash
# Check pod status
kubectl describe pod <pod-name> -n fintech

# View logs
kubectl logs <pod-name> -n fintech

# Check service endpoints
kubectl get endpoints -n fintech
```

### Database connection issues

```bash
# Test PostgreSQL connection
kubectl run postgres-client --rm -i -t --image=postgres:15-alpine -- \
  psql -h postgres-accounts -U accounts_user -d accounts_db
```

### Kafka issues

```bash
# Check Kafka topics
kubectl get kafkatopic -n fintech-infra

# Check Kafka broker logs
kubectl logs -f deployment/kafka-broker-0 -n fintech-infra
```

### ArgoCD sync issues

```bash
# Check application status
kubectl get application -n argocd

# Check ArgoCD logs
kubectl logs -f deployment/argocd-server -n argocd
```

## 📚 Documentation

- [Helm Chart Values Reference](./charts/base-service/values.yaml)
- [Service API Documentation](./services/)
- [ArgoCD Project Configuration](./fintech/argocd/)

## 🤝 Contributing

When adding new services:

1. Create service directory: `services/<service-name>`
2. Add Dockerfile and requirements.txt
3. Create values file: `fintech/services/<service-name>/values.yaml`
4. Update ApplicationSet generator in `fintech/argocd/values-appset.yaml`
5. Re-deploy: `scripts/setup-fintech.sh`

## 📄 License

MIT License

## 🎯 Next Steps

1. **Build and push images** to your registry
2. **Update image repository** in service values files
3. **Deploy to staging** using ArgoCD
4. **Test API endpoints** with provided curl commands
5. **Monitor metrics** in Prometheus
6. **Review fraud alerts** in audit database
7. **Scale services** by adjusting HPA settings

# Makefile for Fintech Project

.PHONY: help install-argocd setup-fintech build-services test-services clean

help:
	@echo "Fintech System Commands"
	@echo "======================"
	@echo "make install-argocd     - Install ArgoCD"
	@echo "make setup-fintech      - Deploy fintech system (includes Kafka topics)"
	@echo "make install-strimzi    - Install Strimzi Kafka operator"
	@echo "make build-services     - Build Docker images"
	@echo "make test-services      - Run service tests"
	@echo "make start-local        - Start services locally with docker-compose"
	@echo "make stop-local         - Stop local services"
	@echo "make clean              - Clean up resources"

install-argocd:
	scripts/install-argocd.sh

install-strimzi:
	helm repo add strimzi https://strimzi.io/charts || true
	helm upgrade --install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
	  --namespace strimzi-system --create-namespace --wait

setup-fintech:
	scripts/setup-fintech.sh

build-services:
	scripts/build-services.sh

test-services:
	scripts/test-services.sh

start-local:
	docker-compose up -d

stop-local:
	docker-compose down

status:
	@echo "Namespaces:"
	kubectl get ns | grep fintech || echo "No fintech namespaces found"
	@echo ""
	@echo "Services in fintech:"
	kubectl get pods -n fintech 2>/dev/null || echo "fintech namespace not found"
	@echo ""
	@echo "Services in fintech-infra:"
	kubectl get pods -n fintech-infra 2>/dev/null || echo "fintech-infra namespace not found"

ports:
	@echo "Port-forwarding services..."
	@echo ""
	@echo "Account Service:      kubectl port-forward svc/account-service -n fintech 8001:8080"
	@echo "Transaction Service:  kubectl port-forward svc/transaction-service -n fintech 8002:8080"
	@echo "Ledger Service:       kubectl port-forward svc/ledger-service -n fintech 8003:8080"
	@echo "Settlement Service:   kubectl port-forward svc/settlement-service -n fintech 8004:8080"
	@echo "Fraud Detection:      kubectl port-forward svc/fraud-detection-service -n fintech 8005:8080"
	@echo ""
	@echo "ArgoCD:               kubectl port-forward svc/argocd-server -n argocd 8080:443"

logs-account:
	kubectl logs -f deployment/account-service -n fintech

logs-transaction:
	kubectl logs -f deployment/transaction-service -n fintech

logs-ledger:
	kubectl logs -f deployment/ledger-service -n fintech

logs-settlement:
	kubectl logs -f deployment/settlement-service -n fintech

logs-fraud:
	kubectl logs -f deployment/fraud-detection-service -n fintech

describe-pods:
	@echo "Account Service:"
	kubectl describe pod -l app.kubernetes.io/name=account-service -n fintech | head -30
	@echo ""
	@echo "Transaction Service:"
	kubectl describe pod -l app.kubernetes.io/name=transaction-service -n fintech | head -30

clean:
	@echo "Cleaning up fintech system..."
	helm uninstall account-service -n fintech 2>/dev/null || true
	helm uninstall transaction-service -n fintech 2>/dev/null || true
	helm uninstall ledger-service -n fintech 2>/dev/null || true
	helm uninstall settlement-service -n fintech 2>/dev/null || true
	helm uninstall fraud-detection-service -n fintech 2>/dev/null || true
	helm uninstall fintech-appset -n argocd 2>/dev/null || true
	helm uninstall fintech-project -n argocd 2>/dev/null || true
	helm uninstall fintech-kafka -n fintech-infra 2>/dev/null || true
	helm uninstall postgres-accounts -n fintech-infra 2>/dev/null || true
	helm uninstall postgres-ledger -n fintech-infra 2>/dev/null || true
	helm uninstall postgres-audit -n fintech-infra 2>/dev/null || true
	kubectl delete ns fintech 2>/dev/null || true
	kubectl delete ns fintech-infra 2>/dev/null || true
	@echo "Cleanup complete"

full-clean: clean
	@echo "Removing ArgoCD..."
	kubectl delete ns argocd 2>/dev/null || true
	@echo "Full cleanup complete"

.DEFAULT_GOAL := help

#!/bin/bash
set -e

echo "================================"
echo "Installing ArgoCD"
echo "================================"

# Create argocd namespace
kubectl create namespace argocd || echo "Namespace argocd already exists"

# Install ArgoCD
kubectl apply --server-side -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
echo "Waiting for ArgoCD to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd || true
kubectl wait --for=condition=available --timeout=300s deployment/argocd-application-controller -n argocd || true

echo ""
echo "================================"
echo "ArgoCD Installation Complete"
echo "================================"
echo ""
echo "Patch ArgoCD to use insecure mode (for local development):"
kubectl patch configmap argocd-cmd-params-cm -n argocd -p '{"data":{"server.insecure":"true"}}' || true

echo ""
echo "Get the initial admin password:"
echo ""
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo

echo ""
echo "Port-forward to access ArgoCD:"
echo "kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo ""
echo "Then access at: https://localhost:8080"
echo "Default username: admin"

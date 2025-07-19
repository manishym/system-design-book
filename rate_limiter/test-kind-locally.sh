#!/bin/bash

# Test Kind cluster setup locally
# This script mimics the GitHub Actions workflow to test Kind cluster setup

set -e

echo "🚀 Testing Kind cluster setup locally..."

# Check if Kind is installed
if ! command -v kind &> /dev/null; then
    echo "❌ Kind is not installed. Please install it first:"
    echo "   brew install kind  # macOS"
    echo "   # or follow: https://kind.sigs.k8s.io/docs/user/quick-start/#installation"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed. Please install it first"
    exit 1
fi

# Check if helm is installed  
if ! command -v helm &> /dev/null; then
    echo "❌ Helm is not installed. Please install it first"
    exit 1
fi

# Cleanup any existing cluster
echo "🧹 Cleaning up any existing Kind cluster..."
kind delete cluster --name kind || true

echo "🔧 Creating Kind cluster..."
kind create cluster --name kind --image kindest/node:v1.27.3 --wait 300s

echo "✅ Verifying cluster is ready..."
kubectl cluster-info --context kind-kind
kubectl get nodes
kubectl wait --for=condition=Ready nodes --all --timeout=300s

echo "🐳 Building Docker image..."
docker build -t rate-limiter:test .

echo "📋 Verifying image was built..."
docker images | grep rate-limiter

echo "🧪 Testing image locally..."
timeout 10s docker run --rm rate-limiter:test --help || echo "⚠️ Image test failed (expected for help command)"

echo "📦 Loading image into Kind cluster..."
kind load docker-image rate-limiter:test --name kind

echo "✅ Verifying image is available in Kind cluster..."
docker exec kind-control-plane crictl images | grep rate-limiter || echo "⚠️ Image not found in cluster"

echo "🧪 Testing image availability with test pod..."
kubectl apply -f k8s/test-image-pod.yaml

# Wait for pod to finish (either succeed or fail)
echo "Waiting for test pod to complete..."
for i in {1..30}; do
  STATUS=$(kubectl get pod test-image-pod -o jsonpath='{.status.phase}')
  if [ "$STATUS" = "Succeeded" ] || [ "$STATUS" = "Failed" ]; then
    break
  fi
  echo "Pod status: $STATUS, waiting..."
  sleep 2
done

# Check final status
FINAL_STATUS=$(kubectl get pod test-image-pod -o jsonpath='{.status.phase}')
echo "Final pod status: $FINAL_STATUS"

# Get logs regardless of status
echo "Pod logs:"
kubectl logs test-image-pod || echo "No logs available"

if [ "$FINAL_STATUS" != "Succeeded" ]; then
  echo "❌ Test pod failed with status: $FINAL_STATUS"
  kubectl describe pod test-image-pod
  kubectl delete pod test-image-pod --ignore-not-found=true
  exit 1
fi

echo "✅ Test pod completed successfully"
kubectl delete pod test-image-pod

echo "📦 Installing Redis..."
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

helm install redis bitnami/redis \
  --set auth.enabled=false \
  --set replica.replicaCount=1 \
  --set architecture=standalone \
  --wait --timeout=300s

echo "✅ Verifying Redis is ready..."
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=redis --timeout=300s

echo "🔍 Checking Redis service details..."
kubectl get services | grep redis
kubectl get pods -l app.kubernetes.io/name=redis -o wide

echo "🧪 Testing Redis connectivity with debug pod..."
kubectl apply -f k8s/debug-pod.yaml || echo "Debug pod already exists"
kubectl wait --for=condition=Ready pod/debug-pod --timeout=60s || echo "Debug pod not ready, continuing..."

if kubectl get pod debug-pod &>/dev/null; then
  echo "Testing Redis connectivity from debug pod..."
  kubectl exec debug-pod -- nslookup redis-master || echo "DNS lookup failed"
  kubectl exec debug-pod -- nc -zv redis-master 6379 || echo "Redis connection failed"
fi

echo "🚀 Deploying Rate Limiter..."
kubectl apply -f k8s/deployment-ci.yaml
kubectl apply -f k8s/service.yaml

echo "📊 Checking initial deployment status..."
kubectl get deployment rate-limiter -o wide
kubectl get pods -l app=rate-limiter -o wide

echo "⏳ Waiting for deployment to be ready..."
if ! kubectl rollout status deployment/rate-limiter --timeout=300s; then
  echo "❌ Deployment failed to roll out. Debugging..."
  echo "=== Deployment Status ==="
  kubectl get deployment rate-limiter -o yaml
  echo "=== Pod Status ==="
  kubectl get pods -l app=rate-limiter -o wide
  echo "=== Pod Logs ==="
  kubectl logs -l app=rate-limiter --tail=50 || echo "No logs available"
  echo "=== Events ==="
  kubectl get events --sort-by=.metadata.creationTimestamp
  echo "=== Describe Pods ==="
  kubectl describe pods -l app=rate-limiter
  echo "=== Docker Images in Cluster ==="
  docker exec kind-control-plane crictl images | grep rate-limiter || echo "❌ rate-limiter image not found in cluster!"
  echo "=== All Images in Cluster ==="
  docker exec kind-control-plane crictl images
  echo "=== Redis Services ==="
  kubectl get services | grep redis
  exit 1
fi

kubectl wait --for=condition=Ready pod -l app=rate-limiter --timeout=120s

echo "🔍 Checking all services..."
kubectl get pods -o wide
kubectl get services

echo "🎯 Testing the deployment..."
kubectl port-forward svc/rate-limiter 8080:80 &
PORT_FORWARD_PID=$!

sleep 10

# Test health endpoint
echo "Testing health endpoint..."
curl -f http://localhost:8080/health || {
    echo "❌ Health check failed"
    kubectl logs -l app=rate-limiter --tail=50
    kill $PORT_FORWARD_PID || true
    exit 1
}

echo "✅ Health check passed!"

# Clean up port forward
kill $PORT_FORWARD_PID || true

echo "🧹 Cleaning up..."
kubectl delete deployment rate-limiter --ignore-not-found=true
kubectl delete service rate-limiter --ignore-not-found=true
kubectl delete pod debug-pod --ignore-not-found=true
kubectl delete pod test-image-pod --ignore-not-found=true
helm uninstall redis --ignore-not-found=true
kind delete cluster --name kind

echo "🎉 Kind cluster test completed successfully!"
#!/bin/bash
set -e

echo "🚀 Testing Consistent Hashing System with Kind (Simple)"

# Export separate kubeconfig to avoid K3s conflicts
export KUBECONFIG=./kind-kubeconfig

# Cleanup any existing cluster
echo "🧹 Cleaning up existing cluster..."
kind delete cluster --name test-consistent-hashing 2>/dev/null || true

# Create simple Kind cluster (single node)
echo "🏗️ Creating simple Kind cluster..."
cat <<EOF | kind create cluster --name test-consistent-hashing --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: test-consistent-hashing
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30000
    hostPort: 30000
    protocol: TCP
EOF

echo "⏳ Waiting for cluster to be ready..."
kubectl cluster-info --context kind-test-consistent-hashing
kubectl wait --for=condition=Ready nodes --all --timeout=300s

# Build and test Docker images locally first
echo "🐳 Building and testing Docker images..."
docker build -f gateway/Dockerfile -t consistent-hashing/gateway:test .
docker build -f storage/kvstore/Dockerfile -t consistent-hashing/kvstore:test .

# Test gateway image
echo "🧪 Testing gateway image..."
if ! docker run --rm consistent-hashing/gateway:test python -c "from simple_hash_ring import SimpleHashRing; print('Gateway image works')"; then
  echo "❌ Gateway image test failed"
  exit 1
fi

# Test kvstore image
echo "🧪 Testing kvstore image..."
if ! docker run --rm consistent-hashing/kvstore:test python -c "import kvstore_service; print('KVStore image works')"; then
  echo "❌ KVStore image test failed"
  exit 1
fi

# Load images into Kind cluster
echo "📦 Loading images into Kind cluster..."
kind load docker-image consistent-hashing/gateway:test --name test-consistent-hashing
kind load docker-image consistent-hashing/kvstore:test --name test-consistent-hashing

# Create namespace
echo "🏠 Creating namespace..."
kubectl create namespace consistent-hashing

# Deploy with reduced replicas for testing
echo "🌐 Deploying gateway (single replica)..."
sed 's|image: consistent-hashing/gateway:latest|image: consistent-hashing/gateway:test|g' k8s/gateway-deployment.yaml | \
sed 's|imagePullPolicy: Never|imagePullPolicy: IfNotPresent|g' | \
sed 's|replicas: 3|replicas: 1|g' | \
kubectl apply -f -

echo "🗄️ Deploying kvstore (single replica)..."
sed 's|image: consistent-hashing/kvstore:latest|image: consistent-hashing/kvstore:test|g' k8s/kvstore-deployment.yaml | \
sed 's|imagePullPolicy: Never|imagePullPolicy: IfNotPresent|g' | \
sed 's|replicas: 3|replicas: 1|g' | \
kubectl apply -f -

echo "🔍 Checking pod status..."
kubectl get pods -n consistent-hashing -o wide

echo "📋 Waiting for gateway pod..."
timeout 300 kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=gateway -n consistent-hashing || {
  echo "❌ Gateway pod failed to become ready"
  kubectl get pods -n consistent-hashing
  kubectl describe pods -l app.kubernetes.io/name=gateway -n consistent-hashing
  kubectl logs -l app.kubernetes.io/name=gateway -n consistent-hashing --tail=50 || true
  exit 1
}

echo "📋 Waiting for kvstore pod..."
timeout 300 kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=kvstore -n consistent-hashing || {
  echo "❌ KVStore pod failed to become ready"
  kubectl get pods -n consistent-hashing
  kubectl describe pods -l app.kubernetes.io/name=kvstore -n consistent-hashing
  kubectl logs -l app.kubernetes.io/name=kvstore -n consistent-hashing --tail=50 || true
  exit 1
}

echo "✅ All pods are ready!"
kubectl get pods -n consistent-hashing -o wide

# Quick functional test
echo "🧪 Running quick functional test..."
kubectl port-forward svc/gateway-service 8000:8000 -n consistent-hashing &
PF_PID=$!

sleep 5

# Test endpoints
if curl -f -s http://localhost:8000/ring/status > /dev/null; then
  echo "✅ Gateway health check passed"
else
  echo "❌ Gateway health check failed"
  kill $PF_PID 2>/dev/null || true
  exit 1
fi

if curl -f -s http://localhost:8000/nodes > /dev/null; then
  echo "✅ Nodes endpoint test passed"
else
  echo "❌ Nodes endpoint test failed"
  kill $PF_PID 2>/dev/null || true
  exit 1
fi

kill $PF_PID 2>/dev/null || true

echo "🎉 Simple Kind test completed successfully!"
echo "🧹 Cleaning up..."
kind delete cluster --name test-consistent-hashing
rm -f ./kind-kubeconfig 